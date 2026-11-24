// 울대모(Uldaemo) 비주얼 임팩트 엔진 (3D 폭죽, 번개 성사 축하 배너, 폭파 애니메이션)
// =========================================================
// ✨ 비주얼 임팩트 엔진 (고해상도 3D 멀티웨이브 폭죽 & 번개 성사 축하 연출)
// =========================================================
let _confettiRafId = null;
let _confettiWaveTimers = [];

function drawStarShape(ctx, spikes, outerR, innerR) {
  let rot = Math.PI / 2 * 3;
  const step = Math.PI / spikes;
  ctx.beginPath();
  ctx.moveTo(0, -outerR);
  for (let i = 0; i < spikes; i++) {
    ctx.lineTo(Math.cos(rot) * outerR, Math.sin(rot) * outerR);
    rot += step;
    ctx.lineTo(Math.cos(rot) * innerR, Math.sin(rot) * innerR);
    rot += step;
  }
  ctx.closePath();
  ctx.fill();
}

function fireConfetti(opts = {}) {
  if (typeof isReducedMotionPreferred === "function" && isReducedMotionPreferred()) return;
  const canvas = document.getElementById("confetti-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const W = window.innerWidth;
  const H = window.innerHeight;
  canvas.width = Math.floor(W * dpr);
  canvas.height = Math.floor(H * dpr);
  canvas.style.width = W + "px";
  canvas.style.height = H + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  if (_confettiRafId) cancelAnimationFrame(_confettiRafId);
  _confettiWaveTimers.forEach(t => clearTimeout(t));
  _confettiWaveTimers = [];

  const isMatchMode = (opts && opts.mode === "match");
  const palette = [
    "#287D62", "#34D399", "#A7F3D0", // 에메랄드 · 소프트 민트
    "#F59E0B", "#FBBF24", "#FDE68A", // 샴페인 골드 · 앰버
    "#FB7185", "#38BDF8", "#A78BFA", "#FFFFFF" // 코랄 · 스카이 · 바이올렛 · 화이트
  ];
  const shapes = ["ribbon", "ribbon", "circle", "star", "streamer"];
  const pieces = [];
  const shockwaves = [];

  function spawnCannonBurst(originX, originY, baseAngleRad, spreadRad, count, minSpeed, maxSpeed) {
    for (let i = 0; i < count; i++) {
      const angle = baseAngleRad + (Math.random() - 0.5) * spreadRad;
      const speed = minSpeed + Math.random() * (maxSpeed - minSpeed);
      const shape = shapes[Math.floor(Math.random() * shapes.length)];
      pieces.push({
        x: originX + (Math.random() - 0.5) * 24,
        y: originY + (Math.random() - 0.5) * 18,
        prevX: originX,
        prevY: originY,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        gravity: shape === "streamer" ? 0.19 : 0.26 + Math.random() * 0.08,
        drag: 0.962 + Math.random() * 0.015,
        size: shape === "star" ? (Math.random() * 4.5 + 5.5) : (Math.random() * 6.5 + 6),
        color: palette[Math.floor(Math.random() * palette.length)],
        shape,
        rot: Math.random() * Math.PI * 2,
        vrot: (Math.random() - 0.5) * 0.22,
        tiltAngle: Math.random() * Math.PI * 2,
        tiltSpeed: 0.11 + Math.random() * 0.14,
        rollAngle: Math.random() * Math.PI * 2,
        rollSpeed: 0.08 + Math.random() * 0.12,
        swayAmp: 0.35 + Math.random() * 0.65,
        swaySpeed: 0.06 + Math.random() * 0.05,
        swayOffset: Math.random() * Math.PI * 2,
        alpha: 1,
        decay: 0.011 + Math.random() * 0.008,
        isSpark: false
      });
    }
  }

  function spawnAerialFirework(cx, cy, count, ringColor) {
    shockwaves.push({
      x: cx,
      y: cy,
      r: 6,
      maxR: isMatchMode ? 115 : 85,
      alpha: 0.78,
      color: ringColor || "#34D399"
    });
    for (let i = 0; i < count; i++) {
      const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.18;
      const speed = 3.5 + Math.random() * 9.5;
      const isStar = Math.random() > 0.45;
      pieces.push({
        x: cx,
        y: cy,
        prevX: cx,
        prevY: cy,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - 1.2,
        gravity: 0.16,
        drag: 0.945,
        size: isStar ? (Math.random() * 4 + 4.5) : (Math.random() * 3.5 + 3),
        color: palette[Math.floor(Math.random() * palette.length)],
        shape: isStar ? "star" : "circle",
        rot: Math.random() * Math.PI * 2,
        vrot: (Math.random() - 0.5) * 0.25,
        tiltAngle: Math.random() * Math.PI,
        tiltSpeed: 0.15,
        rollAngle: 0,
        rollSpeed: 0.1,
        swayAmp: 0.15,
        swaySpeed: 0.05,
        swayOffset: 0,
        alpha: 1,
        decay: 0.016 + Math.random() * 0.01,
        isSpark: true
      });
    }
  }

  // 1단계 (0ms): 좌·우 대각선 트윈 캐논 + 중앙 팡파르 분수 발사
  spawnCannonBurst(W * 0.12, H * 0.68, -Math.PI * 0.36, 0.52, isMatchMode ? 42 : 30, 12, 23);
  spawnCannonBurst(W * 0.88, H * 0.68, -Math.PI * 0.64, 0.52, isMatchMode ? 42 : 30, 12, 23);
  spawnAerialFirework(W * 0.50, H * 0.36, isMatchMode ? 36 : 26, "#FBBF24");

  // 2단계 (170ms & 330ms): 상단 공중 스타버스트 불꽃놀이 연쇄 개화
  _confettiWaveTimers.push(setTimeout(() => {
    spawnAerialFirework(W * 0.30, H * 0.28, isMatchMode ? 32 : 22, "#34D399");
  }, 170));
  _confettiWaveTimers.push(setTimeout(() => {
    spawnAerialFirework(W * 0.70, H * 0.26, isMatchMode ? 34 : 22, "#F59E0B");
  }, 330));

  let frame = 0;
  const maxFrames = 165;

  function tick() {
    frame++;
    ctx.clearRect(0, 0, W, H);
    let alive = false;

    // 쇼크웨이브 링 렌더링
    for (let i = shockwaves.length - 1; i >= 0; i--) {
      const sw = shockwaves[i];
      sw.r += (sw.maxR - sw.r) * 0.14;
      sw.alpha -= 0.036;
      if (sw.alpha > 0.01) {
        alive = true;
        ctx.save();
        ctx.globalAlpha = Math.max(0, sw.alpha);
        ctx.strokeStyle = sw.color;
        ctx.lineWidth = 2.5 * sw.alpha + 0.8;
        ctx.beginPath();
        ctx.arc(sw.x, sw.y, sw.r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      } else {
        shockwaves.splice(i, 1);
      }
    }

    // 3D 파티클 & 불꽃 스파크 렌더링
    for (let i = 0; i < pieces.length; i++) {
      const p = pieces[i];
      p.prevX = p.x;
      p.prevY = p.y;
      p.vx *= p.drag;
      p.vy = Math.min(6.8, p.vy * p.drag + p.gravity);
      p.x += p.vx + Math.sin(frame * p.swaySpeed + p.swayOffset) * p.swayAmp;
      p.y += p.vy;
      p.rot += p.vrot;
      p.tiltAngle += p.tiltSpeed;
      p.rollAngle += p.rollSpeed;

      if (frame > 38 || p.isSpark) {
        p.alpha -= p.decay;
      }

      if (p.alpha > 0.01 && p.y < H + 35) {
        alive = true;
        ctx.save();
        ctx.globalAlpha = Math.max(0, p.alpha);

        // 공중 폭죽 스파크 잔상 꼬리(Trail)
        if (p.isSpark && Math.hypot(p.x - p.prevX, p.y - p.prevY) > 1.8) {
          ctx.strokeStyle = p.color;
          ctx.lineWidth = Math.max(1.2, p.size * 0.32);
          ctx.lineCap = "round";
          ctx.beginPath();
          ctx.moveTo(p.prevX, p.prevY);
          ctx.lineTo(p.x, p.y);
          ctx.stroke();
        }

        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.fillStyle = p.color;

        const scaleX = Math.cos(p.tiltAngle);
        const scaleY = 0.55 + 0.45 * Math.abs(Math.sin(p.rollAngle));

        if (p.shape === "star") {
          ctx.scale(0.75 + 0.25 * Math.abs(scaleX), 0.75 + 0.25 * scaleY);
          drawStarShape(ctx, 4, p.size, p.size * 0.42);
        } else if (p.shape === "circle") {
          ctx.scale(Math.max(0.25, Math.abs(scaleX)), scaleY);
          ctx.beginPath();
          ctx.arc(0, 0, p.size * 0.48, 0, Math.PI * 2);
          ctx.fill();
        } else if (p.shape === "streamer") {
          ctx.scale(scaleX, 1);
          ctx.fillRect(-p.size * 0.22, -p.size * 0.85, p.size * 0.44, p.size * 1.7);
        } else {
          // 3D 텀블링 리본 콘페티
          ctx.scale(scaleX, scaleY);
          ctx.fillRect(-p.size * 0.55, -p.size * 0.35, p.size * 1.1, p.size * 0.7);
        }
        ctx.restore();
      }
    }

    if (alive && frame < maxFrames) {
      _confettiRafId = requestAnimationFrame(tick);
    } else {
      ctx.clearRect(0, 0, W, H);
      _confettiRafId = null;
    }
  }

  _confettiRafId = requestAnimationFrame(tick);
}

function triggerLightningFlash() {
  const el = document.getElementById("flash-overlay");
  if (!el) return;
  el.style.opacity = "1";
  setTimeout(() => { el.style.opacity = "0"; }, 380);
}

let _matchCelebrationTimer = null;
function showMeetupMatchCelebration(post, applicantUser, mode = "match") {
  const hostUser = (post && DB.users[post.author_id]) || DB.users[state.user_id] || { avatar: "🐶", nickname: "방장" };
  const apUser = applicantUser || { avatar: "⚡", nickname: "학우" };
  const hostAvatar = String(hostUser.avatar || "🐶").split(" ")[0];
  const apAvatar = mode === "create"
    ? (typeof getCatEmoji === "function" && post ? getCatEmoji(post.category, post.title) : "⚡")
    : String(apUser.avatar || "🐱").split(" ")[0];
  const titleTxt = post ? post.title : "캠퍼스 번개";
  const badgeLabel = mode === "create" ? "⚡ 오픈" : (mode === "apply" ? "🙌 신청" : "⚡ 매칭");
  const topMainTxt = mode === "create"
    ? "🎉 새 번개 모임 오픈!"
    : (mode === "apply" ? "⚡ 번개 참여 신청 완료!" : "🎉 번개 모임 성사!");
  const topSubTxt = mode === "create"
    ? `· ${escHtml(post && post.location ? post.location : "실시간 모집 시작")}`
    : (mode === "apply" ? "· 방장 수락 시 대화방 오픈" : "· 안심 대화방 오픈");
  const bottomTxt = mode === "create"
    ? `[${escHtml(titleTxt)}] 모임이 등록되었어요!`
    : (mode === "apply"
      ? `[${escHtml(titleTxt)}] 모임에 참여를 신청했어요!`
      : `${escHtml(apUser.nickname || "학우")}님과 [${escHtml(titleTxt)}] 매칭 완료!`);

  let banner = document.getElementById("meetup-match-celebration");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "meetup-match-celebration";
    document.body.appendChild(banner);
  }
  banner.className = "match-celebration-banner";
  banner.onclick = () => {
    banner.classList.add("is-hiding");
    setTimeout(() => { if (banner && banner.parentElement) banner.remove(); }, 260);
  };
  const _esc = (typeof escHtml === "function") ? escHtml : (s => String(s || "").replace(/[&<>"']/g, m => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[m])));
  banner.innerHTML = `
    <div class="match-avatar-pair">
      <span class="match-avatar-circle">${_esc(hostAvatar)}</span>
      <span class="match-avatar-circle second">${_esc(apAvatar)}</span>
      <span class="match-spark-badge">${_esc(badgeLabel)}</span>
    </div>
    <div style="min-width:0; flex:1;">
      <div style="display:flex; align-items:center; gap:6px; margin-bottom:2px;">
        <span style="font-size:11px; font-weight:800; color:#34D399; letter-spacing:0.02em;">${_esc(topMainTxt)}</span>
        <span style="font-size:11px; color:#9CA3AF; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${_esc(topSubTxt)}</span>
      </div>
      <div style="font-size:14px; font-weight:800; color:#FFFFFF; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
        ${bottomTxt}
      </div>
    </div>
  `;

  clearTimeout(_matchCelebrationTimer);
  _matchCelebrationTimer = setTimeout(() => {
    if (banner && banner.parentElement) {
      banner.classList.add("is-hiding");
      setTimeout(() => { if (banner && banner.parentElement) banner.remove(); }, 280);
    }
  }, 3100);
}

// 번개 폭파/취소 시 펑! 하고 터지는 연기·파편 폭발 애니메이션
function fireBurstExplosion(x, y) {
  const canvas = document.getElementById("confetti-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  const originX = x || (canvas.width * 0.5);
  const originY = y || (canvas.height * 0.45);
  const colors = ["#EF4444", "#F59E0B", "#6B7280", "#9CA3AF", "#DC2626", "#FBBF24", "#1F2937"];
  const particles = Array.from({ length: 65 }, () => {
    const angle = Math.random() * Math.PI * 2;
    const speed = Math.random() * 16 + 4;
    return {
      x: originX,
      y: originY,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed - 2,
      size: Math.random() * 9 + 4,
      color: colors[Math.floor(Math.random() * colors.length)],
      isSmoke: Math.random() > 0.4,
      alpha: 1
    };
  });
  let frame = 0;
  function tick() {
    frame++;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    let alive = false;
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      p.vx *= 0.94;
      p.vy = p.vy * 0.94 + (p.isSmoke ? -0.1 : 0.35); // 연기는 위로 피어오르고 파편은 떨어짐
      p.size += p.isSmoke ? 0.35 : 0;
      p.alpha -= p.isSmoke ? 0.022 : 0.028;
      if (p.alpha > 0) {
        alive = true;
        ctx.save();
        ctx.globalAlpha = Math.max(0, p.alpha);
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    });
    if (alive && frame < 70) requestAnimationFrame(tick);
    else ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
  requestAnimationFrame(tick);
}

