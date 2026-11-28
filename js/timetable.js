// 울대모(Uldaemo) 내 시간표 · 공강 메이트 매칭 모듈
const TT_DAYS = ["월", "화", "수", "목", "금"];
// 에브리타임 시간대 기준: 1(9시) ~ 11(오후 7시, 19:00~20:00)
const TT_PERIODS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];

// 과목별 구분을 위한 에브리타임 감성 파스텔·에디토리얼 팔레트 (10색)
const TT_COURSE_PALETTE = [
  { bg: "#E7F5EE", border: "#9AD4BA", text: "#14533E", accent: "#287D62" }, // Forest Mint
  { bg: "#FFF4DF", border: "#F0CC86", text: "#7A4F0B", accent: "#D99B26" }, // Warm Amber
  { bg: "#E8F1FE", border: "#9EC2FA", text: "#1B4A8A", accent: "#4285F4" }, // Sky Blue
  { bg: "#F2EBFE", border: "#C4B0F8", text: "#4C2A85", accent: "#7C52D9" }, // Soft Lavender
  { bg: "#FDECEC", border: "#F5AEAE", text: "#8C2323", accent: "#E05A5A" }, // Coral Rose
  { bg: "#E5F6F5", border: "#8CD3CE", text: "#135955", accent: "#2A9D8F" }, // Ocean Teal
  { bg: "#FFF0E6", border: "#F5BA93", text: "#8A3F14", accent: "#E07A3F" }, // Warm Peach
  { bg: "#EEF7E4", border: "#B2D98A", text: "#365C14", accent: "#6BA336" }, // Fresh Olive
  { bg: "#FCEBF4", border: "#F0A8CE", text: "#852056", accent: "#D65094" }, // Berry Pink
  { bg: "#EAEFFB", border: "#A6B9F2", text: "#243B82", accent: "#5271D9" }, // Periwinkle Indigo
];

function periodToEverytimeHour(p) {
  const h = 8 + Number(p); // 9..19
  return h > 12 ? String(h - 12) : String(h);
}

function formatEverytimeSlotRange(day, periods) {
  const sorted = [...(periods || [])].map(Number).sort((a, b) => a - b);
  if (!sorted.length) return "수업 칸 선택";
  const first = periodToEverytimeHour(sorted[0]);
  const lastEndH = 9 + sorted[sorted.length - 1];
  const lastEndStr = lastEndH > 12 ? String(lastEndH - 12) : String(lastEndH);
  return `${day} ${first}~${lastEndStr}시`;
}

function buildCourseColorMap(draft, namesMap) {
  const map = {};
  let idx = 0;
  TT_DAYS.forEach(d => {
    const busy = Array.isArray(draft && draft[d]) ? draft[d].map(Number).sort((a, b) => a - b) : [];
    busy.forEach(p => {
      const nm = String((namesMap && namesMap[`${d}_${p}`]) || "").trim();
      if (nm && !map[nm]) {
        map[nm] = TT_COURSE_PALETTE[idx % TT_COURSE_PALETTE.length];
        idx += 1;
      }
    });
  });
  return map;
}

function buildMergedDayItems(day, draft, namesMap) {
  const busySet = new Set(Array.isArray(draft && draft[day]) ? draft[day].map(Number) : []);
  const items = [];
  let p = 1;
  while (p <= TT_PERIODS.length) {
    if (!busySet.has(p)) {
      items.push({ type: "empty", day, period: p });
      p += 1;
      continue;
    }
    const name = String((namesMap && namesMap[`${day}_${p}`]) || "").trim();
    const periods = [p];
    if (name) {
      let next = p + 1;
      while (next <= TT_PERIODS.length && busySet.has(next)) {
        const nextName = String((namesMap && namesMap[`${day}_${next}`]) || "").trim();
        if (nextName === name) {
          periods.push(next);
          next += 1;
        } else {
          break;
        }
      }
    }
    items.push({
      type: "block",
      day,
      start: periods[0],
      end: periods[periods.length - 1],
      periods,
      name
    });
    p = periods[periods.length - 1] + 1;
  }
  return items;
}

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
  if (isNaN(h) || h < 9 || h > 19) return null;
  return h - 8; // 09:xx -> 1(9시), 13:xx -> 5(오후 1시), 19:xx -> 11(오후 7시)
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
    state._tt_names_draft = JSON.parse(JSON.stringify(u.timetable_names || {}));
  }
  state._tt_selected_slots = null;
  state.timetable_tab = tab || (hasUserTimetable(state.user_id) ? "mates" : "edit");
  state.active_modal = "timetable";
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeTimetableModal() {
  state._tt_draft = null;
  state._tt_names_draft = null;
  state._tt_selected_slots = null;
  state.active_modal = null;
  render();
}

function ensureTimetableDrafts() {
  const u = (DB && DB.users && DB.users[state.user_id]) || {};
  if (!state._tt_draft) state._tt_draft = JSON.parse(JSON.stringify(u.timetable || {}));
  if (!state._tt_names_draft) state._tt_names_draft = JSON.parse(JSON.stringify(u.timetable_names || {}));
}

function addTimetableEmptySlot(day, period) {
  ensureTimetableDrafts();
  const p = Number(period);
  const arr = Array.isArray(state._tt_draft[day]) ? state._tt_draft[day].map(Number) : [];
  if (!arr.includes(p)) {
    arr.push(p);
    arr.sort((a, b) => a - b);
    state._tt_draft[day] = arr;
  }
  state._tt_selected_slots = [`${day}_${p}`];
  render();
  const inp = document.getElementById("tt-course-name-input");
  if (inp) inp.focus();
}

function selectTimetableBlock(day, periodsCsv) {
  ensureTimetableDrafts();
  const periods = String(periodsCsv || "").split(",").map(Number).filter(n => !isNaN(n));
  const keys = periods.map(p => `${day}_${p}`);
  const cur = Array.isArray(state._tt_selected_slots) ? state._tt_selected_slots : [];
  const sameSelection = cur.length === keys.length && cur.every((k, i) => k === keys[i]);
  if (sameSelection && keys.length === 1 && !(state._tt_names_draft && state._tt_names_draft[keys[0]])) {
    // 이름 없는 단일 칸을 한 번 더 누르면 바로 해제
    deleteSelectedTimetableSlots();
    return;
  }
  state._tt_selected_slots = keys;
  render();
}

function deleteSelectedTimetableSlots() {
  ensureTimetableDrafts();
  const sel = Array.isArray(state._tt_selected_slots) ? state._tt_selected_slots : [];
  if (!sel.length) return;
  sel.forEach(slotKey => {
    const [d, pStr] = slotKey.split("_");
    const p = Number(pStr);
    const arr = Array.isArray(state._tt_draft[d]) ? state._tt_draft[d].map(Number) : [];
    state._tt_draft[d] = arr.filter(x => x !== p);
    if (state._tt_names_draft) delete state._tt_names_draft[slotKey];
  });
  state._tt_selected_slots = null;
  render();
}

function updateSelectedSlotCourseName(val) {
  ensureTimetableDrafts();
  const sel = Array.isArray(state._tt_selected_slots) ? state._tt_selected_slots : [];
  if (!sel.length) return;
  const clean = String(val || "").trim().slice(0, 60);
  sel.forEach(slotKey => {
    if (clean) state._tt_names_draft[slotKey] = clean;
    else delete state._tt_names_draft[slotKey];
  });
  const blockEl = document.getElementById(`tt_block_${sel[0]}`);
  if (blockEl) {
    const nameSpan = blockEl.querySelector(".tt-et-block-name");
    if (nameSpan) nameSpan.textContent = clean || "수업";
    const colorMap = buildCourseColorMap(state._tt_draft, state._tt_names_draft);
    const pal = (clean && colorMap[clean]) ? colorMap[clean] : TT_COURSE_PALETTE[0];
    blockEl.style.background = pal.bg;
    blockEl.style.borderColor = pal.border;
    blockEl.style.color = pal.text;
    blockEl.style.borderLeftColor = pal.accent;
  }
}

function triggerTimetableImageUpload() {
  if (state._tt_ai_loading) return;
  const inp = document.getElementById("tt-image-upload-input");
  if (inp) {
    inp.value = "";
    inp.click();
  }
}

function compressTimetableImageToBase64(file, maxDim = 1080, quality = 0.82) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("파일을 읽을 수 없어요."));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("이미지 형식을 확인할 수 없어요."));
      img.onload = () => {
        try {
          let w = img.naturalWidth || img.width;
          let h = img.naturalHeight || img.height;
          if (w > maxDim || h > maxDim) {
            if (w >= h) {
              h = Math.round((h * maxDim) / w);
              w = maxDim;
            } else {
              w = Math.round((w * maxDim) / h);
              h = maxDim;
            }
          }
          const canvas = document.createElement("canvas");
          canvas.width = Math.max(1, w);
          canvas.height = Math.max(1, h);
          const ctx = canvas.getContext("2d");
          ctx.fillStyle = "#FFFFFF";
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL("image/jpeg", quality);
          resolve(dataUrl);
        } catch (err) {
          reject(err);
        }
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

async function handleTimetableImageUpload(inputEl) {
  const file = inputEl && inputEl.files && inputEl.files[0];
  if (!file) return;
  if (!String(file.type || "").startsWith("image/")) {
    return showToast("이미지 파일(JPG, PNG 등)만 업로드할 수 있어요.");
  }
  state._tt_ai_loading = true;
  render();
  showToast("AI가 시간표 사진을 분석하고 있어요... (약 3~5초)");
  try {
    const dataUrl = await compressTimetableImageToBase64(file, 800, 0.78);
    const authPayload = typeof getApiAuthPayload === "function" ? getApiAuthPayload() : {};
    const res = await fetch("/api/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(Object.assign({}, authPayload, {
        action: "parse_timetable_image",
        image_base64: dataUrl,
        mime_type: "image/jpeg"
      }))
    });
    const data = await res.json();
    state._tt_ai_loading = false;
    if (!data || !data.ok) {
      if (data && data.detail) console.warn("[울대모 시간표 OCR]", data.detail);
      render();
      return showToast((data && data.message) || "시간표 인식에 실패했어요. 다시 시도해 주세요.");
    }
    const cnt = Number(data.count || 0);
    if (cnt === 0) {
      render();
      return showToast("사진에서 수업을 찾지 못했어요. 요일과 시간이 잘 보이는 캡처로 올려주세요.");
    }
    state._tt_draft = data.timetable || {};
    state._tt_names_draft = data.timetable_names || {};
    state._tt_selected_slots = null;
    render();
    showToast(`AI가 수업 ${cnt}칸을 자동으로 채웠어요! 확인 후 [시간표 저장]을 눌러주세요.`);
  } catch (e) {
    state._tt_ai_loading = false;
    render();
    showToast("시간표 분석 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.");
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
  state._tt_selected_slots = null;
  render();
  showToast("시간표를 초기화했어요.");
}

function saveUserTimetable() {
  const u = DB.users[state.user_id];
  if (!u) return;
  const draft = state._tt_draft || {};
  const clean = {};
  TT_DAYS.forEach(d => {
    clean[d] = Array.isArray(draft[d]) ? [...new Set(draft[d].map(Number))].filter(n => n >= 1 && n <= TT_PERIODS.length).sort((a, b) => a - b) : [];
  });
  u.timetable = clean;
  u.timetable_names = state._tt_names_draft || u.timetable_names || {};
  u.timetable_saved = true;
  u.updated_at = Date.now();
  saveDB(true);
  state._tt_draft = null;
  state._tt_names_draft = null;
  state._tt_selected_slots = null;
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
  const selSlots = Array.isArray(state._tt_selected_slots) && state._tt_selected_slots.length ? state._tt_selected_slots : null;
  const selDay = selSlots ? selSlots[0].split("_")[0] : "";
  const selPeriods = selSlots ? selSlots.map(k => Number(k.split("_")[1])).filter(n => !isNaN(n)) : [];
  const selSlotLabel = selSlots ? formatEverytimeSlotRange(selDay, selPeriods) : "수업 선택";
  const selSlotVal = selSlots ? (namesMap[selSlots[0]] || "") : "";
  const colorMap = buildCourseColorMap(draft, namesMap);

  const dayHeadersHtml = TT_DAYS.map((d, di) =>
    `<div class="tt-et-day" style="grid-column:${di + 2}; grid-row:1;">${d}</div>`
  ).join("");

  const hourAxisHtml = TT_PERIODS.map((p, idx) =>
    `<div class="tt-et-hour" style="grid-row:${idx + 2};">${periodToEverytimeHour(p)}</div>`
  ).join("");

  const cellsHtml = TT_DAYS.map((d, di) => {
    const col = di + 2;
    const items = buildMergedDayItems(d, draft, namesMap);
    return items.map(item => {
      if (item.type === "empty") {
        const row = item.period + 1;
        return `<button type="button" class="tt-et-empty" style="grid-column:${col}; grid-row:${row};" onclick="addTimetableEmptySlot('${d}', ${item.period})" aria-label="${d} ${periodToEverytimeHour(item.period)}시 추가"></button>`;
      }
      const rowStart = item.start + 1;
      const rowEnd = item.end + 2;
      const firstKey = `${d}_${item.start}`;
      const pal = (item.name && colorMap[item.name]) ? colorMap[item.name] : TT_COURSE_PALETTE[0];
      const isSelected = Boolean(selSlots && selSlots.includes(firstKey));
      const periodsCsv = item.periods.join(",");
      return `
        <button type="button" id="tt_block_${firstKey}" class="tt-et-block ${isSelected ? 'selected' : ''}"
          style="grid-column:${col}; grid-row:${rowStart} / ${rowEnd}; background:${pal.bg}; border-color:${pal.border}; border-left:3px solid ${pal.accent}; color:${pal.text};"
          onclick="selectTimetableBlock('${d}', '${periodsCsv}')">
          <span class="tt-et-block-name">${escHtml(item.name || "수업")}</span>
        </button>
      `;
    }).join("");
  }).join("");

  const editorHtml = `
    <div style="background:#FFFFFF; border:1.5px solid #E5E8EB; border-radius:20px; padding:18px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <span style="font-size:15px; font-weight:800; color:#191F28;">내 수업 시간표</span>
        <button type="button" onclick="resetTimetableDraft()" style="border:none; background:none; color:#98A2B3; font-size:12px; font-weight:600; cursor:pointer;">초기화</button>
      </div>
      <div id="tt-draft-summary" style="font-size:12px; color:#287D62; font-weight:700; margin-bottom:10px;">
        ${escHtml(buildTimetableDraftSummary(draft))}
      </div>

      <!-- AI 시간표 사진 자동 입력 -->
      <input id="tt-image-upload-input" type="file" accept="image/*" style="display:none;" onchange="handleTimetableImageUpload(this)" />
      <button type="button" onclick="triggerTimetableImageUpload()" ${state._tt_ai_loading ? 'disabled' : ''} style="width:100%; padding:11px 14px; margin-bottom:12px; border-radius:14px; border:1.5px dashed #287D62; background:#EEF8F3; color:#1F6A52; display:flex; align-items:center; justify-content:space-between; gap:10px; cursor:${state._tt_ai_loading ? 'wait' : 'pointer'}; text-align:left; opacity:${state._tt_ai_loading ? '0.75' : '1'};">
        <span style="display:flex; align-items:center; gap:9px; min-width:0;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1F6A52" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
          <span style="min-width:0;">
            <span style="display:block; font-size:13px; font-weight:800; color:#1F6A52;">${state._tt_ai_loading ? 'AI가 시간표를 분석하고 있어요...' : '시간표 사진으로 자동 채우기'}</span>
            <span style="display:block; font-size:11px; font-weight:500; color:#4E5968; margin-top:1px;">에브리타임 · 포털 캡처 업로드 (원본 미저장)</span>
          </span>
        </span>
        <span style="font-size:12px; font-weight:800; color:#287D62; flex-shrink:0;">${state._tt_ai_loading ? '분석중' : '업로드 ›'}</span>
      </button>

      <!-- 에브리타임 기준 시간표 (9시 ~ 오후 7시) -->
      <div class="tt-et-wrap">
        <div class="tt-et-grid">
          <div class="tt-et-corner"></div>
          ${dayHeadersHtml}
          ${hourAxisHtml}
          ${cellsHtml}
        </div>
      </div>

      <!-- 선택 수업명 수정 · 삭제 바 -->
      <div class="tt-et-editor-bar">
        <span id="tt-course-slot-label" style="font-size:11.5px; font-weight:800; color:#287D62; white-space:nowrap;">${escHtml(selSlotLabel)}</span>
        <input id="tt-course-name-input" type="text" maxlength="60" value="${escHtml(selSlotVal)}" ${selSlots ? '' : 'disabled'} placeholder="${selSlots ? '수업명 전체 입력' : '수업 칸을 눌러 수정·삭제'}" oninput="updateSelectedSlotCourseName(this.value)" onchange="render()" style="flex:1; min-width:0; height:32px; border:none; background:transparent; font-size:13px; color:#191F28; outline:none;" />
        ${selSlots ? `<button type="button" class="tt-et-del-btn" onclick="deleteSelectedTimetableSlots()">삭제</button>` : ''}
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
      <div class="v3-modal-head">
        <div class="v3-modal-head-left">
          <button type="button" class="v3-back-btn" onclick="closeTimetableModal()" aria-label="뒤로 가기"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#191F28" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg></button>
          <h1 style="margin:0; font-size:22px; font-weight:800; color:#191F28; line-height:1.25;">시간표 · 공강 메이트</h1>
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
