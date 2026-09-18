import { readdir } from "node:fs/promises";
import { join } from "node:path";

/**
 * 递归扫描一棵目录树，把其中的 Python 文件转换成点号分隔的模块名列表。
 * 含 __init__.py 的目录本身也会产出一个包名；隐式命名空间子目录（没有
 * __init__.py）同样会被枚举 —— 这正是本次要修的坑：CPython 的
 * pkgutil.iter_modules 会静默跳过这类目录，导致 PyInstaller 的
 * --collect-submodules 漏掉其中所有模块（见 #315）。
 */
async function collectPythonModules(directory, prefix) {
  const modules = [];
  const entries = await readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    if (entry.isDirectory() && entry.name !== "__pycache__") {
      modules.push(...(await collectPythonModules(join(directory, entry.name), [...prefix, entry.name])));
    } else if (entry.isFile() && entry.name.endsWith(".py")) {
      const name = entry.name.slice(0, -3);
      modules.push((name === "__init__" ? prefix : [...prefix, name]).join("."));
    }
  }
  return modules;
}

/** Finds Python analysis roots in staged backends, including namespace packages. */
export async function collectPluginBackendModules(pluginsRoot) {
  const modules = [];
  const plugins = await readdir(pluginsRoot, { withFileTypes: true });
  for (const plugin of plugins) {
    if (!plugin.isDirectory()) continue;
    const packageRoot = join(pluginsRoot, plugin.name);
    const entries = await readdir(packageRoot, { withFileTypes: true });
    if (entries.some((entry) => entry.name === "backend" && entry.isDirectory())) {
      modules.push(
        ...(await collectPythonModules(join(packageRoot, "backend"), ["plugins", plugin.name, "backend"])),
      );
    }
  }
  return modules.sort();
}

/**
 * 收集宿主后端（apps/backend）在给定包根下的全部 Python 模块，包括没有
 * __init__.py 的隐式命名空间目录（例如 agent/tools/）。packageRoots 需要与
 * 仓库根 setup.py 里的 HOST_PACKAGES 保持一致（该文件的清单是维护基准，
 * 两处任一变化都要同步另一处）；main.py 是 PyInstaller 的入口脚本本身，
 * 不是隐式导入，不应出现在 packageRoots 里。
 */
export async function collectHostBackendModules(backendRoot, packageRoots) {
  const modules = [];
  for (const packageRoot of packageRoots) {
    modules.push(...(await collectPythonModules(join(backendRoot, packageRoot), [packageRoot])));
  }
  return modules.sort();
}

/**
 * 列出 root 下所有顶层目录中，递归含有至少一个 .py 文件（忽略 __pycache__）
 * 的目录名。用于构建期兜底检查：如果 apps/backend 冒出一个没有登记进
 * HOST_PACKAGE_ROOTS 的新顶层包，这里会把它报出来，而不是被静默漏收 ——
 * 这是 agent.tools.* 那类问题（#315）在整包级别的重演。复用
 * collectPythonModules 的递归遍历，避免第三次实现同样的目录扫描逻辑。
 */
export async function collectTopLevelPythonPackageRoots(root) {
  const entries = await readdir(root, { withFileTypes: true });
  const roots = [];
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === "__pycache__") continue;
    const modules = await collectPythonModules(join(root, entry.name), [entry.name]);
    if (modules.length > 0) {
      roots.push(entry.name);
    }
  }
  return roots.sort();
}
