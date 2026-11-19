// 울대모(Uldaemo) 내 시간표 · 공강 메이트 매칭 모듈
const TT_DAYS = ["월", "화", "수", "목", "금"];
const TT_PERIODS = [1, 2, 3, 4, 5, 6, 7, 8, 9]; // 1교시(09:00) ~ 9교시(17:00)

function getDayLabelFromDateStr(dateStr) {
  if (!dateStr) return "";
  try {
    const dt = new Date(`${dateStr}T12:00:00`);
    if (isNaN(dt.getTime())) return "";
    return ["일", "월", "화", "수", "목", "금", "토"][dt.getDay()] || "";
  } catch (e) {
    return "";
  }
}

function getPeriodFromTimeStr(timeStr) {
  if (!timeStr || !String(timeStr).includes(":")) return null;
  const h = parseInt(String(timeStr).split(":")[0], 10);
  if (isNaN(h) || h < 9 || h > 17) return null;
  return h - 8; // 09:xx -> 1교시, 13:xx -> 5교시, 17:xx -> 9교시
}

function periodToTimeLabel(p) {
  const h = 8 + Number(p);
  return `${String(h).padStart(2, "0")}:00`;
}

function hasUserTimetable(uid) {
  const u = DB && DB.users && DB.users[uid];
  if (!u || !u.timetable || typeof u.timetable !== "object") return false;
  if (u.timetable_saved) return true;
  return TT_DAYS.some(d => Array.isArray(u.timetable[d]) && u.timetable[d].length > 0);
}

function getBusySetForDay(uid, day) {
  const u = DB && DB.users && DB.users[uid];
  const arr = (u && u.timetable && Array.isArray(u.timetable[day])) ? u.timetable[day] : [];
  return new Set(arr.map(Number));
}

function getFreePeriodsForDay(uid, day) {
  if (!TT_DAYS.includes(day) || !hasUserTimetable(uid)) return [];
  const busy = getBusySetForDay(uid, day);
  return TT_PERIODS.filter(p => !busy.has(p));
}

function formatContiguousPeriods(periods) {
  if (!periods || periods.length === 0) return "";
  const sorted = [...periods].sort((a, b) => a - b);
  const ranges = [];
  let start = sorted[0];
  let end = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === end + 1) {
      end = sorted[i];
    } else {
      ranges.push([start, end]);
      start = sorted[i];
      end = sorted[i];
    }
  }
  ranges.push([start, end]);
  return ranges.map(([s, e]) => `${String(8 + s).padStart(2, "0")}:00~${String(9 + e).padStart(2, "0")}:00`).join(", ");
}

function isPostMatchingMyFreeTime(post) {
  if (!post || !state.user_id || !hasUserTimetable(state.user_id)) return false;
  const day = getDayLabelFromDateStr(post.meet_date);
  if (!TT_DAYS.includes(day)) return false;
  const p = getPeriodFromTimeStr(post.meet_time);
  if (!p) return false;
  const busy = getBusySetForDay(state.user_id, day);
  return !busy.has(p);
}

function computeFreeOverlap(uidA, uidB) {
  if (!hasUserTimetable(uidA) || !hasUserTimetable(uidB)) return null;
  const todayDay = getDayLabelFromDateStr(getTodayStr());
  const tmDate = new Date();
  tmDate.setDate(tmDate.getDate() + 1);
  const tmStr = `${tmDate.getFullYear()}-${String(tmDate.getMonth() + 1).padStart(2, "0")}-${String(tmDate.getDate()).padStart(2, "0")}`;
  const tmDay = getDayLabelFromDateStr(tmStr);

  let myTotalFree = 0;
  let overlapTotal = 0;
  let todayOverlapPeriods = [];
  let tomorrowOverlapPeriods = [];
  const dayOverlaps = [];

  TT_DAYS.forEach(d => {
    const myFree = getFreePeriodsForDay(uidA, d);
    const otherFreeSet = new Set(getFreePeriodsForDay(uidB, d));
    myTotalFree += myFree.length;
    const shared = myFree.filter(p => otherFreeSet.has(p));
    if (shared.length > 0) {
      overlapTotal += shared.length;
      dayOverlaps.push({ day: d, periods: shared, text: `${d} ${formatContiguousPeriods(shared)}` });
      if (d === todayDay) todayOverlapPeriods = shared;
      if (d === tmDay) tomorrowOverlapPeriods = shared;
    }
  });

  if (overlapTotal === 0) return null;
  const pct = Math.min(99, Math.round((overlapTotal / Math.max(1, myTotalFree)) * 100));

  let bestMeetDate = getTodayStr();
  let bestMeetTime = "12:00";
  let highlightText = "";

  if (todayOverlapPeriods.length > 0) {
    bestMeetDate = getTodayStr();
    bestMeetTime = periodToTimeLabel(todayOverlapPeriods[0]);
    highlightText = `오늘 ${formatContiguousPeriods(todayOverlapPeriods)} 공강 겹침`;
  } else if (tomorrowOverlapPeriods.length > 0) {
    bestMeetDate = tmStr;
    bestMeetTime = periodToTimeLabel(tomorrowOverlapPeriods[0]);
    highlightText = `내일 ${formatContiguousPeriods(tomorrowOverlapPeriods)} 공강 겹침`;
  } else if (dayOverlaps.length > 0) {
    const first = dayOverlaps[0];
    const targetIdx = ["일", "월", "화", "수", "목", "금", "토"].indexOf(first.day);
    const nowDt = new Date();
    const diff = (targetIdx - nowDt.getDay() + 7) % 7 || 7;
    nowDt.setDate(nowDt.getDate() + diff);
    bestMeetDate = `${nowDt.getFullYear()}-${String(nowDt.getMonth() + 1).padStart(2, "0")}-${String(nowDt.getDate()).padStart(2, "0")}`;
    bestMeetTime = periodToTimeLabel(first.periods[0]);
    highlightText = `${first.text} 공강 겹침`;
  }

  return {
    overlapHours: overlapTotal,
    pct,
    todayHours: todayOverlapPeriods.length,
    highlightText,
    dayOverlaps,
    bestMeetDate,
    bestMeetTime
  };
}

function getGonggangMates() {
  if (!state.user_id || !hasUserTimetable(state.user_id)) return [];
  const mates = [];
  Object.keys(DB.users || {}).forEach(uid => {
    if (String(uid) === String(state.user_id)) return;
    const u = DB.users[uid];
    if (!u || !hasUserTimetable(uid)) return;
    const ov = computeFreeOverlap(state.user_id, uid);
    if (!ov) return;
    mates.push({ uid, user: u, overlap: ov });
  });
  mates.sort((a, b) => {
    if (b.overlap.todayHours !== a.overlap.todayHours) return b.overlap.todayHours - a.overlap.todayHours;
    if (b.overlap.overlapHours !== a.overlap.overlapHours) return b.overlap.overlapHours - a.overlap.overlapHours;
    return (b.user.manner_temp || 36.5) - (a.user.manner_temp || 36.5);
  });
  return mates;
}

function getMyQuickFreeSlotsForCreate() {
  if (!state.user_id || !hasUserTimetable(state.user_id)) return [];
  const slots = [];
  const now = new Date();
  const curHour = now.getHours();
  const todayStr = getTodayStr();
  const todayDay = getDayLabelFromDateStr(todayStr);

  if (TT_DAYS.includes(todayDay)) {
    const freeToday = getFreePeriodsForDay(state.user_id, todayDay).filter(p => (8 + p) >= curHour);
    freeToday.slice(0, 2).forEach(p => {
      const t = periodToTimeLabel(p);
      slots.push({ label: `⚡ 오늘 ${t} 공강`, date: todayStr, time: t });
    });
  }

  const tm = new Date();
  tm.setDate(tm.getDate() + 1);
  const tmStr = `${tm.getFullYear()}-${String(tm.getMonth() + 1).padStart(2, "0")}-${String(tm.getDate()).padStart(2, "0")}`;
  const tmDay = getDayLabelFromDateStr(tmStr);
  if (TT_DAYS.includes(tmDay)) {
    const freeTm = getFreePeriodsForDay(state.user_id, tmDay);
    freeTm.slice(0, 2).forEach(p => {
      const t = periodToTimeLabel(p);
      slots.push({ label: `🗓️ 내일 ${t} 공강`, date: tmStr, time: t });
    });
  }
  return slots;
}

function applyQuickFreeSlotToCreate(dateStr, timeStr) {
  const dateEl = document.getElementById("c_date");
  const timeEl = document.getElementById("c_time");
  if (dateEl) dateEl.value = dateStr;
  if (timeEl) timeEl.value = timeStr;
  document.querySelectorAll(".time-quick-chip").forEach(el => el.classList.remove("active"));
  showToast(`⚡ 내 공강 시간(${dateStr} ${timeStr})으로 맞췄어요!`);
}

function openTimetableModal(tab) {
  const u = DB.users[state.user_id];
  if (u && !state._tt_draft) {
    state._tt_draft = JSON.parse(JSON.stringify(u.timetable || {}));
  }
  state.timetable_tab = tab || (hasUserTimetable(state.user_id) ? "mates" : "edit");
  state.active_modal = "timetable";
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeTimetableModal() {
  state._tt_draft = null;
  state.active_modal = null;
  render();
}

function toggleTimetableSlot(day, period) {
  state._tt_draft = state._tt_draft || {};
  const arr = Array.isArray(state._tt_draft[day]) ? state._tt_draft[day].map(Number) : [];
  const idx = arr.indexOf(Number(period));
  if (idx >= 0) arr.splice(idx, 1);
  else arr.push(Number(period));
  arr.sort((a, b) => a - b);
  state._tt_draft[day] = arr;

  const btn = document.getElementById(`tt_cell_${day}_${period}`);
  if (btn) {
    const isBusy = arr.includes(Number(period));
    btn.style.background = isBusy ? "#287D62" : "#FFFFFF";
    btn.style.color = isBusy ? "#FFFFFF" : "#8B95A1";
    btn.style.borderColor = isBusy ? "#287D62" : "#E5EAE7";
    btn.textContent = isBusy ? "수업" : "공강";
  }
  const summaryEl = document.getElementById("tt-draft-summary");
  if (summaryEl) {
    summaryEl.textContent = buildTimetableDraftSummary(state._tt_draft);
  }
}

function buildTimetableDraftSummary(ttObj) {
  const todayDay = getDayLabelFromDateStr(getTodayStr());
  const targetDay = TT_DAYS.includes(todayDay) ? todayDay : "월";
  const busy = new Set(Array.isArray(ttObj && ttObj[targetDay]) ? ttObj[targetDay].map(Number) : []);
  const free = TT_PERIODS.filter(p => !busy.has(p));
  if (free.length === 0) return `${targetDay}요일은 풀강이에요 😅`;
  if (free.length === TT_PERIODS.length) return `수업 있는 교시를 눌러서 표시해 주세요 (나머지는 자동 공강 처리)`;
  return `${targetDay}요일 공강: ${formatContiguousPeriods(free)}`;
}

function resetTimetableDraft() {
  state._tt_draft = { "월": [], "화": [], "수": [], "목": [], "금": [] };
  render();
  showToast("시간표를 초기화했어요.");
}

function saveUserTimetable() {
  const u = DB.users[state.user_id];
  if (!u) return;
  const draft = state._tt_draft || {};
  const clean = {};
  TT_DAYS.forEach(d => {
    clean[d] = Array.isArray(draft[d]) ? [...new Set(draft[d].map(Number))].sort((a, b) => a - b) : [];
  });
  u.timetable = clean;
  u.timetable_saved = true;
  u.updated_at = Date.now();
  saveDB(true);
  state._tt_draft = null;
  state.timetable_tab = "mates";
  showToast("✅ 시간표가 저장되었어요! 공강이 겹치는 메이트를 확인해 보세요.");
  render();
}

function inviteGonggangMate(mateUid, meetDate, meetTime) {
  const mate = DB.users[mateUid];
  state.prefill_title = "공강 시간 같이 밥약·카공해요!";
  state.prefill_cat = "🍚 밥약";
  state.prefill_date = meetDate || getTodayStr();
  state.prefill_time = meetTime || "12:00";
  state.invite_mate_id = mateUid;
  state.active_modal = "create";
  render();
  if (mate) {
    showToast(`⚡ ${mate.nickname}님과의 공강 시간(${state.prefill_date} ${state.prefill_time})이 자동 입력되었어요!`);
  }
}

function renderTimetableModal() {
  const u = DB.users[state.user_id];
  if (!u) return "";
  const curTab = state.timetable_tab || "mates";
  const draft = state._tt_draft || u.timetable || {};
  const hasSaved = hasUserTimetable(state.user_id);
  const mates = hasSaved ? getGonggangMates() : [];

  return `
    <div class="uldaemo-card" style="padding:18px 16px;">
      <div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:14px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <button type="button" onclick="closeTimetableModal()" style="width:32px; height:32px; border-radius:50%; border:1px solid #E5EAE7; background:#FFFFFF; color:#191F28; font-size:15px; font-weight:800; cursor:pointer; display:inline-flex; align-items:center; justify-content:center;">←</button>
          <div>
            <div style="font-size:17px; font-weight:800; color:#191F28;">🗓️ 내 시간표 · 공강 메이트</div>
            <div style="font-size:11.5px; color:#6B7684;">시간표를 입력하면 공강이 겹치는 학우를 찾아줘요</div>
          </div>
        </div>
        <button type="button" onclick="closeTimetableModal()" style="border:none; background:#F2F4F6; color:#4E5968; border-radius:999px; padding:6px 12px; font-size:12px; font-weight:700; cursor:pointer;">닫기 ✕</button>
      </div>

      <!-- 세그먼트 탭 -->
      <div style="display:inline-flex; width:100%; background:#F2F4F3; padding:4px; border-radius:12px; gap:4px; margin-bottom:16px;">
        <button type="button" onclick="state.timetable_tab='mates'; render();" style="flex:1; border:none; padding:9px 10px; border-radius:9px; font-size:13px; font-weight:700; cursor:pointer; ${curTab==='mates' ? 'background:#FFFFFF; color:#191F28; box-shadow:0 1px 4px rgba(0,0,0,0.08);' : 'background:transparent; color:#8B95A1;'}">
          ⚡ 공강 메이트 (${mates.length})
        </button>
        <button type="button" onclick="state._tt_draft=JSON.parse(JSON.stringify((DB.users[state.user_id]||{}).timetable||{})); state.timetable_tab='edit'; render();" style="flex:1; border:none; padding:9px 10px; border-radius:9px; font-size:13px; font-weight:700; cursor:pointer; ${curTab==='edit' ? 'background:#FFFFFF; color:#191F28; box-shadow:0 1px 4px rgba(0,0,0,0.08);' : 'background:transparent; color:#8B95A1;'}">
          🗓️ 내 시간표 설정
        </button>
      </div>

      ${curTab === "edit" ? `
        <div id="tt-draft-summary" style="background:#F7F9F8; border:1px solid #E5EAE7; border-radius:10px; padding:9px 12px; margin-bottom:12px; font-size:12px; color:#287D62; font-weight:700;">
          ${escHtml(buildTimetableDraftSummary(draft))}
        </div>

        <div style="display:grid; grid-template-columns: 44px repeat(5, 1fr); gap:4px; margin-bottom:14px; user-select:none;">
          <div></div>
          ${TT_DAYS.map(d => `<div style="text-align:center; font-size:12px; font-weight:800; color:#191F28; padding:4px 0;">${d}</div>`).join("")}
          ${TT_PERIODS.map(p => `
            <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; font-size:10.5px; color:#6B7684; font-weight:700; line-height:1.1;">
              <span>${p}교시</span>
              <span style="font-size:9.5px; color:#8B95A1;">${8 + p}:00</span>
            </div>
            ${TT_DAYS.map(d => {
              const isBusy = Array.isArray(draft[d]) && draft[d].map(Number).includes(p);
              return `
                <button type="button" id="tt_cell_${d}_${p}" onclick="toggleTimetableSlot('${d}', ${p})" style="height:34px; border-radius:8px; border:1px solid ${isBusy ? '#287D62' : '#E5EAE7'}; background:${isBusy ? '#287D62' : '#FFFFFF'}; color:${isBusy ? '#FFFFFF' : '#8B95A1'}; font-size:11px; font-weight:700; cursor:pointer; transition:all 0.12s;">
                  ${isBusy ? '수업' : '공강'}
                </button>
              `;
            }).join("")}
          `).join("")}
        </div>

        <div style="display:flex; gap:8px;">
          <button type="button" class="btn" style="flex:0.4; background:#F2F4F6; color:#4E5968;" onclick="resetTimetableDraft()">초기화</button>
          <button type="button" class="btn btn-primary" style="flex:1;" onclick="saveUserTimetable()">✅ 시간표 저장 & 메이트 찾기</button>
        </div>
      ` : `
        ${!hasSaved ? `
          <div style="text-align:center; padding:28px 16px; background:#F7F9F8; border-radius:16px; border:1px dashed #C5E6D6;">
            <div style="font-size:32px; margin-bottom:8px;">🗓️</div>
            <div style="font-size:15px; font-weight:800; color:#191F28; margin-bottom:6px;">내 시간표를 먼저 등록해 주세요!</div>
            <div style="font-size:12.5px; color:#6B7684; margin-bottom:14px; line-height:1.5;">수업 있는 시간만 톡톡 누르면<br>공강이 겹치는 학우들과 자동으로 매칭해 드려요.</div>
            <button type="button" class="btn btn-primary" style="width:auto; padding:0 18px;" onclick="state._tt_draft={}; state.timetable_tab='edit'; render();">10초 만에 시간표 입력하기 ›</button>
          </div>
        ` : (mates.length === 0 ? `
          <div style="text-align:center; padding:28px 16px; background:#F7F9F8; border-radius:16px;">
            <div style="font-size:28px; margin-bottom:8px;">🌱</div>
            <div style="font-size:14.5px; font-weight:800; color:#191F28; margin-bottom:6px;">아직 시간표를 등록한 다른 학우가 없어요</div>
            <div style="font-size:12px; color:#6B7684; margin-bottom:14px;">학우들이 시간표를 등록하면 공강이 겹치는 메이트가 여기에 나타나요!<br>먼저 내 공강 시간에 맞춰 번개를 열어보는 건 어떨까요?</div>
            <button type="button" class="btn btn-primary" style="width:auto; padding:0 16px;" onclick="state.active_modal='create'; render();">⚡ 내 공강에 번개 열기</button>
          </div>
        ` : `
          <div style="display:flex; flex-direction:column; gap:10px;">
            ${mates.map(m => {
              const tier = getTierByTemp(m.user.manner_temp || 36.5);
              return `
                <div style="padding:13px 14px; border-radius:14px; border:1px solid #E5EAE7; background:#FFFFFF; display:flex; align-items:center; justify-content:space-between; gap:10px;">
                  <div style="display:flex; align-items:center; gap:10px; min-width:0; flex:1;">
                    <div style="width:42px; height:42px; border-radius:50%; background:#EEF8F3; display:flex; align-items:center; justify-content:center; font-size:20px; flex-shrink:0;">
                      ${String(m.user.avatar || '🐶').split(' ')[0]}
                    </div>
                    <div style="min-width:0; flex:1;">
                      <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                        <span style="font-size:14px; font-weight:800; color:#191F28;">${escHtml(m.user.nickname || '학우')}</span>
                        <span class="temp-chip" data-tier="${tier.tier}">${tier.displayTemp}°C</span>
                        <span style="font-size:11px; font-weight:800; color:#287D62; background:#EEF8F3; padding:2px 7px; border-radius:999px;">공강 ${m.overlap.pct}% 일치 (주 ${m.overlap.overlapHours}h)</span>
                      </div>
                      <div style="font-size:11.5px; color:#6B7684; margin-top:2px;">${escHtml(m.user.department || '울산대')} · ${escHtml(m.user.mbti || 'MBTI 비공개')}</div>
                      <div style="font-size:11.5px; font-weight:700; color:#1E6B52; margin-top:4px;">🗓️ ${escHtml(m.overlap.highlightText)}</div>
                    </div>
                  </div>
                  <button type="button" onclick="inviteGonggangMate('${m.uid}', '${m.overlap.bestMeetDate}', '${m.overlap.bestMeetTime}')" style="flex-shrink:0; padding:8px 11px; border-radius:10px; border:none; background:#287D62; color:#FFFFFF; font-size:12px; font-weight:800; cursor:pointer;">⚡ 번개 제안</button>
                </div>
              `;
            }).join("")}
          </div>
        `)}
      `}
    </div>
  `;
}
