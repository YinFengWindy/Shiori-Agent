import { ArrowSquareOut } from "@phosphor-icons/react";
import { SITE_MENU_ITEMS, type SiteScreenId } from "../content/siteCopy";
import { useSound } from "../sound/useSound";

interface TitleMenuProps {
  onOpenScreen: (screen: Exclude<SiteScreenId, "title">) => void;
  onOpenSettings: () => void;
}

/** Vertical galgame title menu: 开始 / 人物 / CG 鉴赏 / 下载 / 设置. */
export function TitleMenu({ onOpenScreen, onOpenSettings }: TitleMenuProps) {
  const { playSfx } = useSound();
  const hover = () => playSfx("hover");
  const click = () => playSfx("click");
  return (
    <nav aria-label="标题菜单" className="site-title-menu flex flex-col items-start">
      {SITE_MENU_ITEMS.map((item) => {
        if (item.kind === "external") {
          return (
            <a
              key={item.id}
              href={item.href}
              target="_blank"
              rel="noopener noreferrer"
              onPointerEnter={hover}
              onClick={click}
              className="site-menu-item group flex w-full items-center gap-2 rounded-md font-display"
            >
              <span className="site-menu-marker" aria-hidden="true" />
              <span className="site-menu-label">{item.label}</span>
              <ArrowSquareOut size={16} aria-hidden="true" className="opacity-60 transition-opacity group-hover:opacity-100" />
            </a>
          );
        }
        // The settings modal plays its own "open" sound instead of the click chime.
        const handleClick =
          item.kind === "modal"
            ? onOpenSettings
            : () => {
                click();
                onOpenScreen(item.id);
              };
        return (
          <button
            key={item.id}
            type="button"
            onPointerEnter={hover}
            onClick={handleClick}
            className="site-menu-item group flex w-full items-center gap-2 rounded-md text-left font-display"
          >
            <span className="site-menu-marker" aria-hidden="true" />
            <span className="site-menu-label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
