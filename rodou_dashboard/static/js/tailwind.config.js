/*
 * Registrale — configuração do Tailwind (Play CDN).
 * Fonte da verdade dos tokens visuais. Documentação: docs/tecnico/06_design_system.md
 *
 * Paleta reduzida a 5 famílias:
 *   neutral (stone)  → superfícies, texto, bordas
 *   ink (azul tinta) → destaque, links, seleção, informação
 *   success          → confirmação
 *   warning          → atenção / pendência
 *   danger           → erro / ação destrutiva
 *
 * Os templates antigos usam slate, stone, blue, indigo, purple, teal, rose etc.
 * Em vez de reescrever 6 mil linhas, esses nomes são apelidos das 5 famílias
 * abaixo. Código novo deve usar os nomes canônicos (neutral, ink, success,
 * warning, danger) ou as classes de componente de registrale.css.
 */
(function () {
    const neutral = {
        50: '#fafaf9', 100: '#f5f5f4', 200: '#e7e5e4', 300: '#d6d3d1', 400: '#a8a29e',
        500: '#78716c', 600: '#57534e', 700: '#44403c', 800: '#292524', 900: '#1c1917', 950: '#0c0a09',
    };
    const ink = {
        50: '#f2f6fa', 100: '#e1eaf3', 200: '#c3d4e7', 300: '#97b4d3', 400: '#6a91bb',
        500: '#4874a3', 600: '#365d89', 700: '#2d4c70', 800: '#283f5c', 900: '#24364d', 950: '#162232',
    };
    const success = {
        50: '#effaf4', 100: '#d8f2e3', 200: '#b3e4c9', 300: '#7fcfa6', 400: '#4bb380',
        500: '#2a9663', 600: '#1e7a50', 700: '#1a6143', 800: '#184e37', 900: '#15402f', 950: '#0a241a',
    };
    const warning = {
        50: '#fdf8ec', 100: '#f9edcb', 200: '#f2d993', 300: '#eac05a', 400: '#e2a733',
        500: '#cf8a1d', 600: '#b06b16', 700: '#8d5016', 800: '#743f18', 900: '#613518', 950: '#381b09',
    };
    const danger = {
        50: '#fdf3f2', 100: '#fbe3e1', 200: '#f7ccc8', 300: '#f0a8a1', 400: '#e5776d',
        500: '#d64f43', 600: '#bf3a2e', 700: '#9f2e24', 800: '#842a23', 900: '#6e2822', 950: '#3c100d',
    };

    tailwind.config = {
        darkMode: 'class',
        theme: {
            extend: {
                colors: {
                    neutral, ink, success, warning, danger,
                    // Apelidos legados (não usar em código novo)
                    slate: neutral, stone: neutral, gray: neutral, zinc: neutral,
                    blue: ink, indigo: ink, sky: ink, purple: ink, violet: ink, cyan: ink,
                    emerald: success, green: success, teal: success,
                    amber: warning, orange: warning, yellow: warning,
                    red: danger, rose: danger, pink: danger,
                },
                fontFamily: {
                    sans: ['"IBM Plex Sans"', 'system-ui', '"Segoe UI"', 'sans-serif'],
                    mono: ['"IBM Plex Mono"', 'ui-monospace', 'Consolas', 'monospace'],
                },
                // Escala de peso enxuta: 400 texto · 500 rótulos · 600 títulos/ênfase
                fontWeight: {
                    bold: '600', extrabold: '600', black: '600',
                },
                letterSpacing: {
                    tighter: '-0.02em', tight: '-0.01em', wide: '0.02em', wider: '0.04em', widest: '0.06em',
                },
                // Raios: 4 · 6 · 8 · 12 (+ full)
                borderRadius: {
                    sm: '4px', DEFAULT: '6px', md: '6px', lg: '8px', xl: '8px', '2xl': '12px', '3xl': '12px',
                },
                boxShadow: {
                    xs: 'var(--shadow-1)', sm: 'var(--shadow-1)', DEFAULT: 'var(--shadow-1)',
                    md: 'var(--shadow-2)', lg: 'var(--shadow-2)',
                    xl: 'var(--shadow-3)', '2xl': 'var(--shadow-3)',
                },
            },
        },
    };
})();
