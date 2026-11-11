/** Праздничное конфетти поверх страницы — за верный ответ, отличный тест, новое достижение.
 * Без библиотек: один canvas на ~2 секунды. Если в системе отключена анимация — ничего не делает. */

const TOKENS = ["--brand", "--pink", "--sun", "--sky", "--mint", "--grape"];

export function confetti({ count = 120, originY = 0.35, tokens = TOKENS }: { count?: number; originY?: number; tokens?: string[] } = {}): void {
  if (typeof window === "undefined" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const style = getComputedStyle(document.documentElement);
  const colors = tokens.map((t) => style.getPropertyValue(t).trim()).filter(Boolean);

  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  Object.assign(canvas.style, { position: "fixed", inset: "0", width: "100%", height: "100%", pointerEvents: "none", zIndex: "9999" });
  document.body.appendChild(canvas);
  const dpr = window.devicePixelRatio || 1;
  const w = window.innerWidth;
  const h = window.innerHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(dpr, dpr);

  // Два залпа — слева и справа, навстречу друг другу.
  const pieces = Array.from({ length: count }, (_, i) => {
    const left = i % 2 === 0;
    const angle = (left ? -60 : -120) * (Math.PI / 180) + (Math.random() - 0.5) * 0.9;
    const speed = 9 + Math.random() * 9;
    return {
      x: left ? w * 0.15 : w * 0.85,
      y: h * originY + 80,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      size: 6 + Math.random() * 6,
      rot: Math.random() * Math.PI,
      spin: (Math.random() - 0.5) * 0.3,
      color: colors[i % colors.length] || "#4f46e5",
      round: Math.random() < 0.3,
    };
  });

  const start = performance.now();
  const frame = (now: number) => {
    const t = now - start;
    ctx.clearRect(0, 0, w, h);
    ctx.globalAlpha = Math.max(0, 1 - Math.max(0, t - 1400) / 600);
    for (const p of pieces) {
      p.vy += 0.35;
      p.vx *= 0.99;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.spin;
      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillStyle = p.color;
      if (p.round) {
        ctx.beginPath();
        ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
        ctx.fill();
      } else ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
      ctx.restore();
    }
    if (t < 2000) requestAnimationFrame(frame);
    else canvas.remove();
  };
  requestAnimationFrame(frame);
}

/** Один праздник на ключ за сессию браузера — чтобы конфетти не повторялось при каждом открытии страницы. */
export function celebrateOnce(key: string, options?: Parameters<typeof confetti>[0]): void {
  try {
    if (sessionStorage.getItem(`celebrated:${key}`)) return;
    sessionStorage.setItem(`celebrated:${key}`, "1");
  } catch {}
  confetti(options);
}
