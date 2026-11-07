"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  RadioTower,
  FileVideo,
  Settings,
  Search,
  Moon,
  Sun,
  ShieldCheck,
  X,
} from "lucide-react";
import { useTheme } from "next-themes";

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();
  const { theme, setTheme } = useTheme();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  if (!open) return null;

  const items = [
    { label: "Dashboard Operations", icon: LayoutDashboard, href: "/dashboard", group: "Navigation" },
    { label: "Live Camera Wall", icon: RadioTower, href: "/live", group: "Navigation" },
    { label: "Video Batches", icon: FileVideo, href: "/videos", group: "Navigation" },
    { label: "Settings & Models", icon: Settings, href: "/settings/model", group: "Settings" },
    { label: "Users & RBAC Access", icon: ShieldCheck, href: "/settings/users", group: "Settings" },
    { label: "Usage & Limits Quota", icon: Settings, href: "/settings/billing", group: "Settings" },
  ];

  const filtered = items.filter((item) =>
    item.label.toLowerCase().includes(query.toLowerCase())
  );

  const handleSelect = (href: string) => {
    router.push(href);
    setOpen(false);
    setQuery("");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/50 p-4 pt-20 backdrop-blur-sm"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-[var(--border)] bg-[var(--surface)] p-2 shadow-[var(--shadow-3)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-[var(--border)] px-3 py-2">
          <Search className="h-4 w-4 text-[var(--text-muted)]" />
          <input
            type="text"
            placeholder="Type a command or navigate... (Cmd+K)"
            className="w-full bg-transparent text-sm text-[var(--text)] outline-none placeholder:text-[var(--text-subtle)]"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <button
            onClick={() => setOpen(false)}
            className="rounded p-1 text-[var(--text-muted)] hover:bg-[var(--surface-sunken)]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {filtered.length === 0 ? (
            <p className="px-3 py-4 text-center text-xs text-[var(--text-muted)]">No results found.</p>
          ) : (
            filtered.map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.href}
                  onClick={() => handleSelect(item.href)}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-[var(--text)] hover:bg-[var(--surface-sunken)]"
                >
                  <Icon className="h-4 w-4 text-[var(--accent)]" />
                  <span>{item.label}</span>
                  <span className="ml-auto text-xs text-[var(--text-subtle)]">{item.group}</span>
                </button>
              );
            })
          )}

          <div className="mt-2 border-t border-[var(--border)] pt-2">
            <button
              onClick={() => {
                setTheme(theme === "dark" ? "light" : "dark");
                setOpen(false);
              }}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm text-[var(--text)] hover:bg-[var(--surface-sunken)]"
            >
              {theme === "dark" ? <Sun className="h-4 w-4 text-[var(--warning-text)]" /> : <Moon className="h-4 w-4 text-[var(--accent)]" />}
              <span>Toggle theme ({theme === "dark" ? "Light Mode" : "Dark Mode"})</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
