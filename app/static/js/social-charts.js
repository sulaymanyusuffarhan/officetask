/* Accessible, dependency-free SVG charts for saved social media analytics. */
(function (root) {
  "use strict";
  function htmlEscape(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  }
  function renderBarChart(rows, key, title, formatter = value => String(value)) {
    const usable = rows.filter(row => row[key] !== null && row[key] !== undefined && Number.isFinite(Number(row[key])));
    if (!usable.length) {
      return `<section class="panel"><h3>${htmlEscape(title)}</h3><div class="empty">No reported values for this metric in the selected period. Missing data is N/A, not zero.</div></section>`;
    }
    const max = Math.max(1, ...usable.map(row => Math.abs(Number(row[key]))));
    const width = 760, labelX = 6, zeroX = 200, plot = 530, rowHeight = 30;
    const height = rows.length * rowHeight + 28, scale = plot / max;
    const elements = rows.map((row, index) => {
      const y = 24 + index * rowHeight;
      const label = htmlEscape(`${row.period ? `${row.period} · ` : ""}${row.series_name || row.platform_name || row.platform}`.slice(0, 40));
      const value = row[key];
      if (value === null || value === undefined) {
        return `<text x="${labelX}" y="${y + 13}" font-size="11">${label}</text><text x="${zeroX + 6}" y="${y + 13}" font-size="11" fill="#66758a">N/A</text>`;
      }
      const number = Number(value), bar = Math.max(2, Math.abs(number) * scale);
      const x = number >= 0 ? zeroX : zeroX - bar, color = number >= 0 ? "#2b6f9b" : "#a83939";
      const valueX = Math.min(width - 4, Math.max(zeroX + bar + 6, zeroX - bar - 45));
      return `<text x="${labelX}" y="${y + 13}" font-size="11">${label}</text><rect x="${x}" y="${y}" width="${bar}" height="18" rx="3" fill="${color}"/><text x="${valueX}" y="${y + 13}" font-size="11">${htmlEscape(formatter(number))}</text>`;
    }).join("");
    return `<section class="panel"><h3>${htmlEscape(title)}</h3><div class="social-svg-wrap"><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${htmlEscape(title)} bar chart">${elements}</svg></div></section>`;
  }
  const api = Object.freeze({ renderBarChart });
  root.SocialCharts = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
