"use client";

import { useEffect, useState } from "react";

type ThemeMode = "dark" | "light";

const STORAGE_KEY = "opscanvas-theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeMode>("dark");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const initialTheme =
      stored === "light" || stored === "dark"
        ? stored
        : window.matchMedia("(prefers-color-scheme: light)").matches
          ? "light"
          : "dark";

    setTheme(initialTheme);
    document.documentElement.dataset.theme = initialTheme;
  }, []);

  function updateTheme(nextTheme: ThemeMode) {
    setTheme(nextTheme);
    document.documentElement.dataset.theme = nextTheme;
    window.localStorage.setItem(STORAGE_KEY, nextTheme);
  }

  return (
    <div className="theme-toggle" aria-label="Theme">
      <button
        aria-pressed={theme === "dark"}
        className={theme === "dark" ? "is-active" : ""}
        onClick={() => updateTheme("dark")}
        type="button"
      >
        Dark
      </button>
      <button
        aria-pressed={theme === "light"}
        className={theme === "light" ? "is-active" : ""}
        onClick={() => updateTheme("light")}
        type="button"
      >
        Light
      </button>
    </div>
  );
}
