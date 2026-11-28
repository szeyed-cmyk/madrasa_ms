/** Rebuild CSS:  npx tailwindcss@3.4.19 -c frontend/tailwind.config.js -i frontend/input.css -o static/app.css --minify
 *  1.0.5: "brand" (primary) and "accent" (secondary) read CSS variables printed by templates/_base.html from
 *  Settings > Branding, so the colours change without a rebuild. The older `emerald-*` classes are the brand colour too. */
const v = (name) => {
  const out = {};
  for (const s of [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]) out[s] = `rgb(var(--${name}-${s}) / <alpha-value>)`;
  return out;
};
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js", "./app/**/*.py"],
  theme: {
    extend: {
      colors: { brand: v("brand"), accent: v("accent"), emerald: v("brand") },
      fontFamily: {
        sans: ["InterVariable", "Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Noto Sans", "Noto Sans Bengali", "Nirmala UI", "Noto Sans Arabic", "Segoe UI", "Arial", "sans-serif"],
        display: ["Plus Jakarta Sans Variable", "InterVariable", "ui-sans-serif", "system-ui", "Segoe UI", "Noto Sans Bengali", "Nirmala UI", "Noto Kufi Arabic", "Noto Sans Arabic", "sans-serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgb(15 23 42 / 0.04), 0 4px 16px -4px rgb(15 23 42 / 0.08)",
        lift: "0 2px 4px rgb(15 23 42 / 0.04), 0 18px 40px -12px rgb(15 23 42 / 0.18)",
        glow: "0 10px 30px -10px rgb(var(--brand-600) / 0.55)",
      },
      keyframes: {
        "fade-in-up": { "0%": { opacity: "0", transform: "translateY(12px)" }, "100%": { opacity: "1", transform: "translateY(0)" } },
        "scale-in": { "0%": { opacity: "0", transform: "scale(0.96)" }, "100%": { opacity: "1", transform: "scale(1)" } },
        "soft-pulse": { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.65" } },
        float: { "0%, 100%": { transform: "translateY(0px)" }, "50%": { transform: "translateY(-8px)" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        progress: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(250%)" } },
        "toast-in": { "0%": { opacity: "0", transform: "translateY(10px) scale(0.98)" }, "100%": { opacity: "1", transform: "translateY(0) scale(1)" } },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.45s ease-out both",
        "scale-in": "scale-in 0.28s ease-out",
        "soft-pulse": "soft-pulse 2.2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        float: "float 5s ease-in-out infinite",
        shimmer: "shimmer 1.6s infinite",
        progress: "progress 1.1s ease-in-out infinite",
        "toast-in": "toast-in 0.25s ease-out",
      },
    },
  },
  plugins: [],
};
