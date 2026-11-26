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
  state._tt_names_draft = state._tt_names_draft || JSON.parse(JSON.stringify((DB.users[state.user_id] && DB.users[state.user_id].timetable_names) || {}));
  const arr = Array.isArray(state._tt_draft[day]) ? state._tt_draft[day].map(Number) : [];
  const idx = arr.indexOf(Number(period));
  const slotKey = `${day}_${period}`;
  if (idx >= 0) {
    arr.splice(idx, 1);
    delete state._tt_names_draft[slotKey];
    if (state._tt_selected_slot === slotKey) state._tt_selected_slot = null;
  } else {
    arr.push(Number(period));
    state._tt_selected_slot = slotKey;
  }
  arr.sort((a, b) => a - b);
  state._tt_draft[day] = arr;

  const btn = document.getElementById(`tt_cell_${day}_${period}`);
  if (btn) {
    const isBusy = arr.includes(Number(period));
    const sName = (state._tt_names_draft && state._tt_names_draft[slotKey]) ? String(state._tt_names_draft[slotKey]).slice(0, 4) : "수업";
    btn.style.background = isBusy ? "#287D62" : "#FFFFFF";
    btn.style.color = isBusy ? "#FFFFFF" : "#98A2B3";
    btn.style.borderColor = isBusy ? "#287D62" : "transparent";
    btn.textContent = isBusy ? sName : "";
  }
  const summaryEl = document.getElementById("tt-draft-summary");
  if (summaryEl) {
    summaryEl.textContent = buildTimetableDraftSummary(state._tt_draft);
  }
  const courseInput = document.getElementById("tt-course-name-input");
  const courseLabel = document.getElementById("tt-course-slot-label");
  if (courseInput && courseLabel) {
    if (state._tt_selected_slot) {
      const [sd, sp] = state._tt_selected_slot.split("_");
      courseLabel.textContent = `${sd} ${sp}교시 수업명`;
      courseInput.value = (state._tt_names_draft && state._tt_names_draft[state._tt_selected_slot]) || "";
      courseInput.disabled = false;
    } else {
      courseLabel.textContent = "수업 칸 선택";
      courseInput.value = "";
      courseInput.disabled = true;
    }
  }
}

function updateSelectedSlotCourseName(val) {
  if (!state._tt_selected_slot) return;
  state._tt_names_draft = state._tt_names_draft || {};
  const clean = String(val || "").trim().slice(0, 12);
  if (clean) state._tt_names_draft[state._tt_selected_slot] = clean;
  else delete state._tt_names_draft[state._tt_selected_slot];
  const [sd, sp] = state._tt_selected_slot.split("_");
  const btn = document.getElementById(`tt_cell_${sd}_${sp}`);
  if (btn) {
    btn.textContent = clean ? clean.slice(0, 4) : "수업";
  }
}

function buildTimetableDraftSummary(ttObj) {
  const todayDay = getDayLabelFromDateStr(getTodayStr());
  const targetDay = TT_DAYS.includes(todayDay) ? todayDay : "월";
  const busy = new Set(Array.isArray(ttObj && ttObj[targetDay]) ? ttObj[targetDay].map(Number) : []);
  const free = TT_PERIODS.filter(p => !busy.has(p));
  if (free.length === 0) return `${targetDay}요일은 풀강이에요`;
  if (free.length === TT_PERIODS.length) return `수업이 있는 칸만 눌러주세요 (빈 칸은 자동 공강)`;
  return `${targetDay}요일 내 공강 · ${formatContiguousPeriods(free)}`;
}

function resetTimetableDraft() {
  state._tt_draft = { "월": [], "화": [], "수": [], "목": [], "금": [] };
  state._tt_names_draft = {};
  state._tt_selected_slot = null;
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
  u.timetable_names = state._tt_names_draft || u.timetable_names || {};
  u.timetable_saved = true;
  u.updated_at = Date.now();
  saveDB(true);
  state._tt_draft = null;
  state._tt_names_draft = null;
  state._tt_selected_slot = null;
  state.timetable_tab = "mates";
  showToast("시간표가 저장되었어요! 공강이 겹치는 학우를 확인해 보세요.");
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
    showToast(`${mate.nickname}님과의 공강 시간(${state.prefill_date} ${state.prefill_time})이 자동 입력되었어요.`);
  }
}

function renderTimetableModal() {
  const u = DB.users[state.user_id];
  if (!u) return "";
  const curTab = state.timetable_tab || "mates";
  const draft = state._tt_draft || u.timetable || {};
  const namesMap = state._tt_names_draft || u.timetable_names || {};
  const hasSaved = hasUserTimetable(state.user_id);
  const mates = hasSaved ? getGonggangMates() : [];
  const selSlot = state._tt_selected_slot || null;
  const selSlotLabel = selSlot ? `${selSlot.split("_")[0]} ${selSlot.split("_")[1]}교시 수업명` : "수업 칸 선택";
  const selSlotVal = selSlot ? (namesMap[selSlot] || "") : "";

  const editorHtml = `
    <div style="background:#FFFFFF; border:1.5px solid #E5E8EB; border-radius:20px; padding:18px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <span style="font-size:15px; font-weight:800; color:#191F28;">내 수업 시간표</span>
        <button type="button" onclick="resetTimetableDraft()" style="border:none; background:none; color:#98A2B3; font-size:12px; font-weight:600; cursor:pointer;">초기화</button>
      </div>
      <div id="tt-draft-summary" style="font-size:12px; color:#287D62; font-weight:700; margin-bottom:12px;">
        ${escHtml(buildTimetableDraftSummary(draft))}
      </div>

      <div style="background:#F7F9F8; border-radius:16px; padding:12px 10px; margin-bottom:12px;">
        <div style="display:grid; grid-template-columns: 36px repeat(5, 1fr); gap:5px; user-select:none;">
          <div></div>
          ${TT_DAYS.map(d => `<div style="text-align:center; font-size:12px; font-weight:700; color:#6B7684; padding:2px 0 4px;">${d}</div>`).join("")}
          ${TT_PERIODS.map(p => `
            <div style="display:flex; align-items:center; justify-content:center; font-size:11px; color:#98A2B3; font-weight:700;">
              ${p}
            </div>
            ${TT_DAYS.map(d => {
              const isBusy = Array.isArray(draft[d]) && draft[d].map(Number).includes(p);
              const sName = namesMap[`${d}_${p}`] ? String(namesMap[`${d}_${p}`]).slice(0, 4) : "수업";
              return `
                <button type="button" id="tt_cell_${d}_${p}" onclick="toggleTimetableSlot('${d}', ${p})" style="height:32px; border-radius:8px; border:1px solid ${isBusy ? '#287D62' : 'transparent'}; background:${isBusy ? '#287D62' : '#FFFFFF'}; color:${isBusy ? '#FFFFFF' : '#98A2B3'}; font-size:10.5px; font-weight:700; cursor:pointer; transition:all 0.12s; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                  ${isBusy ? escHtml(sName) : ''}
                </button>
              `;
            }).join("")}
          `).join("")}
        </div>
      </div>

      <!-- 선택 칸 수업명 한 줄 입력 (선택) -->
      <div style="display:flex; align-items:center; gap:8px; background:#F7F9F8; border-radius:14px; padding:6px 10px 6px 14px; margin-bottom:14px;">
        <span id="tt-course-slot-label" style="font-size:11.5px; font-weight:700; color:#6B7684; white-space:nowrap;">${escHtml(selSlotLabel)}</span>
        <input id="tt-course-name-input" type="text" maxlength="12" value="${escHtml(selSlotVal)}" ${selSlot ? '' : 'disabled'} placeholder="수업명 입력 (선택)" oninput="updateSelectedSlotCourseName(this.value)" style="flex:1; min-width:0; height:32px; border:none; background:transparent; font-size:13px; color:#191F28; outline:none;" />
      </div>

      <button type="button" onclick="saveUserTimetable()" style="width:100%; height:46px; border-radius:23px; border:none; background:#287D62; color:#FFFFFF; font-size:14.5px; font-weight:800; cursor:pointer;">시간표 저장</button>
    </div>
  `;

  const matesHtml = `
    <div style="background:#FFFFFF; border:1.5px solid #E5E8EB; border-radius:20px; padding:18px;">
      <div style="font-size:15px; font-weight:800; color:#191F28; margin-bottom:4px;">공강이 겹치는 학우 ${mates.length}명</div>
      <div style="font-size:12px; color:#6B7684; margin-bottom:14px;">단과대와 매너온도만 블라인드로 표시돼요</div>

      ${!hasSaved ? `
        <div style="text-align:center; padding:32px 16px; background:#F7F9F8; border-radius:16px;">
          <div style="font-size:14.5px; font-weight:800; color:#191F28; margin-bottom:6px;">내 시간표를 먼저 등록해 주세요</div>
          <div style="font-size:12.5px; color:#6B7684; margin-bottom:14px; line-height:1.5;">수업 있는 칸만 누르면 공강이 겹치는 학우를 찾아드려요.</div>
          ${!isPC() ? `<button type="button" onclick="state._tt_draft={}; state.timetable_tab='edit'; render();" style="height:38px; padding:0 18px; border-radius:19px; border:none; background:#287D62; color:#FFFFFF; font-size:13px; font-weight:700; cursor:pointer;">시간표 입력하기 ›</button>` : ''}
        </div>
      ` : (mates.length === 0 ? `
        <div style="text-align:center; padding:32px 16px; background:#F7F9F8; border-radius:16px;">
          <div style="font-size:14.5px; font-weight:800; color:#191F28; margin-bottom:6px;">아직 공강이 겹치는 학우가 없어요</div>
          <div style="font-size:12px; color:#6B7684; margin-bottom:14px;">먼저 내 공강 시간에 맞춰 번개를 열어보는 건 어떨까요?</div>
          <button type="button" onclick="state.active_modal='create'; render();" style="height:38px; padding:0 18px; border-radius:19px; border:none; background:#287D62; color:#FFFFFF; font-size:13px; font-weight:700; cursor:pointer;">내 공강에 번개 열기</button>
        </div>
      ` : `
        <div style="display:flex; flex-direction:column; gap:10px;">
          ${mates.map(m => {
            const tier = getTierByTemp(m.user.manner_temp || 36.5);
            const broadDept = typeof getBroadCollege === "function" ? getBroadCollege(m.user.department) : (m.user.department || "울산대");
            return `
              <div style="padding:14px 16px; border-radius:16px; background:#F7F9F8; display:flex; align-items:center; justify-content:space-between; gap:10px;">
                <div style="min-width:0; flex:1;">
                  <div style="font-size:14.5px; font-weight:800; color:#191F28;">${escHtml(tier.name)} · ${tier.displayTemp}°C · ${escHtml(broadDept)}</div>
                  <div style="font-size:12.5px; font-weight:700; color:#287D62; margin-top:4px;">${escHtml(m.overlap.highlightText)}</div>
                  <div style="font-size:11.5px; color:#6B7684; margin-top:2px;">주 ${m.overlap.overlapHours}시간 공강 일치 (${m.overlap.pct}%)</div>
                </div>
                <button type="button" onclick="inviteGonggangMate('${m.uid}', '${m.overlap.bestMeetDate}', '${m.overlap.bestMeetTime}')" style="flex-shrink:0; height:34px; padding:0 14px; border-radius:17px; border:none; background:#FFFFFF; color:#287D62; font-size:12px; font-weight:700; cursor:pointer;">번개 열기</button>
              </div>
            `;
          }).join("")}
        </div>
      `)}
    </div>
  `;

  return `
    <div style="max-width:920px;">
      <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px;">
        <div style="display:flex; align-items:center; gap:10px;">
          <button type="button" onclick="closeTimetableModal()" style="width:36px; height:36px; border-radius:18px; border:1px solid #E5E8EB; background:#FFFFFF; color:#191F28; font-size:16px; font-weight:700; cursor:pointer; display:inline-flex; align-items:center; justify-content:center;">←</button>
          <h1 style="margin:0; font-size:22px; font-weight:800; color:#191F28;">시간표 · 공강 메이트</h1>
        </div>
      </div>

      ${isPC() ? `
        <div class="pc-tt-2col">
          ${editorHtml}
          ${matesHtml}
        </div>
      ` : `
        <div style="display:flex; gap:8px; margin-bottom:14px;">
          <button type="button" onclick="state.timetable_tab='mates'; render();" style="height:36px; padding:0 16px; border-radius:18px; border:none; background:${curTab === 'mates' ? '#287D62' : '#F7F9F8'}; color:${curTab === 'mates' ? '#FFFFFF' : '#6B7684'}; font-size:13px; font-weight:700; cursor:pointer;">공강 메이트 ${mates.length}</button>
          <button type="button" onclick="state._tt_draft=JSON.parse(JSON.stringify((DB.users[state.user_id]||{}).timetable||{})); state._tt_names_draft=JSON.parse(JSON.stringify((DB.users[state.user_id]||{}).timetable_names||{})); state.timetable_tab='edit'; render();" style="height:36px; padding:0 16px; border-radius:18px; border:none; background:${curTab === 'edit' ? '#287D62' : '#F7F9F8'}; color:${curTab === 'edit' ? '#FFFFFF' : '#6B7684'}; font-size:13px; font-weight:700; cursor:pointer;">내 시간표 입력</button>
        </div>
        ${curTab === 'edit' ? editorHtml : matesHtml}
      `}
    </div>
  `;
}
