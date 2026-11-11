import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { SIZES } from "../lib/store";

export interface TitanApp {
  id: string; title: string; icon: string; blurb: string;
  component: LazyExoticComponent<ComponentType<{ props?: Record<string, unknown> }>>;
  size: [number, number];
}

export const APPS: TitanApp[] = [
  { id: "home", title: "Home", icon: "home", blurb: "Dashboard and widgets", size: [900, 580], component: lazy(() => import("../apps/Home")) },
  { id: "assistant", title: "Assistant", icon: "spark", blurb: "Ask TITAN to do things", size: [820, 600], component: lazy(() => import("../apps/Assistant")) },
  { id: "files", title: "Files", icon: "folder", blurb: "Browse and manage files", size: [940, 580], component: lazy(() => import("../apps/Files")) },
  { id: "terminal", title: "Terminal", icon: "terminal", blurb: "Risk-checked shell", size: [820, 520], component: lazy(() => import("../apps/Terminal")) },
  { id: "monitor", title: "System Monitor", icon: "activity", blurb: "CPU, memory, processes", size: [880, 600], component: lazy(() => import("../apps/Monitor")) },
  { id: "security", title: "Security Centre", icon: "shield", blurb: "Permissions, audit, network", size: [920, 620], component: lazy(() => import("../apps/Security")) },
  { id: "memory", title: "Memory", icon: "brain", blurb: "What TITAN remembers", size: [780, 560], component: lazy(() => import("../apps/Memory")) },
  { id: "tasks", title: "Tasks", icon: "tasks", blurb: "Background work", size: [720, 480], component: lazy(() => import("../apps/Tasks")) },
  { id: "developer", title: "Developer", icon: "code", blurb: "Projects, Git, builds", size: [960, 620], component: lazy(() => import("../apps/Developer")) },
  { id: "web", title: "Web", icon: "globe", blurb: "Search, read, bookmarks", size: [820, 580], component: lazy(() => import("../apps/Web")) },
  { id: "plugins", title: "Plugins", icon: "plug", blurb: "Extensions and permissions", size: [720, 500], component: lazy(() => import("../apps/Plugins")) },
  { id: "settings", title: "Settings", icon: "settings", blurb: "System and personalisation", size: [860, 600], component: lazy(() => import("../apps/Settings")) },
];
export const APP = Object.fromEntries(APPS.map((a) => [a.id, a]));
APPS.forEach((a) => { SIZES[a.id] = a.size; });
export const DEFAULT_DOCK = ["home", "assistant", "files", "terminal", "monitor", "security", "settings"];
