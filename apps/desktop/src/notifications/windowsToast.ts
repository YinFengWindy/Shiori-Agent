import { pathToFileURL } from "node:url";
import { notificationActivationUrl } from "./activation.js";

function xmlText(value: string) {
  // XML 1.0 cannot represent these characters, even as numeric entities.
  return Array.from(value).filter((character) => {
    const code = character.codePointAt(0)!;
    return code === 9 || code === 10 || code === 13
      || (code >= 32 && code <= 0xd7ff) || (code >= 0xe000 && code <= 0xfffd) || code >= 0x10000;
  }).join("").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}

/** Uses a durable OS protocol target rather than Electron's per-notification COM object/tag. */
export function windowsNotificationToast(options: {
  protocol: string;
  roleId: string;
  title: string;
  body: string;
  iconPath: string;
}) {
  const launch = xmlText(notificationActivationUrl(options.protocol, options.roleId));
  const icon = xmlText(pathToFileURL(options.iconPath).href);
  return `<toast activationType="protocol" launch="${launch}"><visual><binding template="ToastGeneric">`
    + `<image placement="appLogoOverride" src="${icon}"/>`
    + `<text>${xmlText(options.title)}</text><text>${xmlText(options.body)}</text>`
    + "</binding></visual></toast>";
}
