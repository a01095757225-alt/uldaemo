// 울대모(Uldaemo) 내 시간표 · 공강 메이트 매칭 모듈
const TT_DAYS = ["월", "화", "수", "목", "금"];
// 에브리타임 시간대 기준: 1(9시) ~ 11(오후 7시, 19:00~20:00)
const TT_PERIODS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];

// 과목별 구분을 위한 Figma T1/T5 토스풍 파스텔 팔레트 (10색)
const TT_COURSE_PALETTE = [
  { bg: "#E8F1FE", text: "#2B6CD8" }, // Sky Blue (대학영어)
  { bg: "#E6F4EE", text: "#1F6A53" }, // Forest Mint (코딩기초)
  { bg: "#F1EBFD", text: "#6741D9" }, // Soft Lavender (미적분학)
  { bg: "#FFF1E6", text: "#D9480F" }, // Warm Peach (ICT개론)
  { bg: "#FDECF1", text: "#C2255C" }, // Coral Rose (물리학)
  { bg: "#E3F6F8", text: "#0C8599" }, // Ocean Cyan (코딩실습)
  { bg: "#FFF6DB", text: "#A66A00" }, // Warm Amber
  { bg: "#EEF7E4", text: "#3B6B16" }, // Fresh Olive
  { bg: "#FCEBF6", text: "#9C2474" }, // Berry Pink
  { bg: "#EAEFFB", text: "#2D47A0" }, // Periwinkle Indigo
];

function periodToEverytimeHour(p) {
  const h = 8 + Number(p); // 9..19
  return h > 12 ? String(h - 12) : String(h);
}

function periodToKoreanHourText(p) {
  const h = 8 + Number(p);
  if (h < 12) return `오전 ${h}시`;
  if (h === 12) return `오후 12시`;
  return `오후 ${h - 12}시`;
}

function formatBlockTimeRange(startP, endP) {
  const sh = 8 + Number(startP);
  const eh = 8 + Number(endP);
  return `${sh}:00–${eh}:50`;
}

function formatEverytimeSlotRange(day, periods) {
  const sorted = [...(periods || [])].map(Number).sort((a, b) => a - b);
  if (!sorted.length) return "수업 선택";
  const first = periodToEverytimeHour(sorted[0]);
  const lastEndH = 9 + sorted[sorted.length - 1];
  const lastEndStr = lastEndH > 12 ? String(lastEndH - 12) : String(lastEndH);
  return `${day}요일 ${first}~${lastEndStr}시`;
}

function minToHHMM(mins) {
  const h = Math.floor(Number(mins) / 60);
  const m = Number(mins) % 60;
  return `${h}:${String(m).padStart(2, "0")}`;
}

function minToKoreanLabel(mins) {
  const h = Math.floor(Number(mins) / 60);
  const m = Number(mins) % 60;
  const ap = h < 12 ? "오전" : "오후";
  const h12 = h > 12 ? h - 12 : h;
  return m === 0 ? `${ap} ${h12}시` : `${ap} ${h12}시 30분`;
}

function buildBlocksFromLegacy(ttObj, namesMap) {
  const blocks = [];
  TT_DAYS.forEach(d => {
    const items = buildMergedDayItems(d, ttObj || {}, namesMap || {});
    items.forEach(it => {
      if (it.type === "block") {
        blocks.push({
          day: d,
          name: it.name || "",
          start_min: (8 + it.start) * 60,
          end_min: (9 + it.end) * 60
        });
      }
    });
  });
  return blocks;
}

function getUserTimetableBlocks(u) {
  if (!u) return [];
  if (Array.isArray(u.timetable_blocks) && u.timetable_blocks.length > 0) {
    return JSON.parse(JSON.stringify(u.timetable_blocks));
  }
  return buildBlocksFromLegacy(u.timetable || {}, u.timetable_names || {});
}

function syncLegacyFromBlocks(blocks) {
  const tt = { "월": [], "화": [], "수": [], "목": [], "금": [] };
  const names = {};
  const sets = { "월": new Set(), "화": new Set(), "수": new Set(), "목": new Set(), "금": new Set() };
  (blocks || []).forEach(b => {
    if (!b || !sets[b.day]) return;
    const sm = Math.max(540, Math.min(1170, Number(b.start_min) || 540));
    const em = Math.max(sm + 30, Math.min(1200, Number(b.end_min) || (sm + 60)));
    const firstH = Math.floor(sm / 60);
    const lastH = Math.floor((em - 1) / 60);
    for (let h = Math.max(9, firstH); h <= Math.min(19, lastH); h++) {
      const p = h - 8;
      if (p >= 1 && p <= TT_PERIODS.length) {
        sets[b.day].add(p);
        if (b.name) names[`${b.day}_${p}`] = b.name;
      }
    }
  });
  TT_DAYS.forEach(d => {
    tt[d] = [...sets[d]].sort((a, b) => a - b);
  });
  return { timetable: tt, timetable_names: names };
}

function buildCourseColorMapFromBlocks(blocks) {
  const map = {};
  let idx = 0;
  const sorted = [...(blocks || [])].sort((a, b) => {
    const di = TT_DAYS.indexOf(a.day) - TT_DAYS.indexOf(b.day);
    return di !== 0 ? di : (a.start_min - b.start_min);
  });
  sorted.forEach(b => {
    const nm = String((b && b.name) || "").trim();
    if (nm && !map[nm]) {
      map[nm] = TT_COURSE_PALETTE[idx % TT_COURSE_PALETTE.length];
      idx += 1;
    }
  });
  return map;
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
  if (u && !state._tt_blocks_draft) {
    state._tt_blocks_draft = getUserTimetableBlocks(u);
    const synced = syncLegacyFromBlocks(state._tt_blocks_draft);
    state._tt_draft = synced.timetable;
    state._tt_names_draft = synced.timetable_names;
  }
  state._tt_sheet = null;
  state.timetable_tab = tab || "mates";
  state.active_modal = "timetable";
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function closeTimetableModal() {
  state._tt_draft = null;
  state._tt_names_draft = null;
  state._tt_blocks_draft = null;
  state._tt_sheet = null;
  state.active_modal = null;
  render();
}

function ensureTimetableDrafts() {
  const u = (DB && DB.users && DB.users[state.user_id]) || {};
  if (!Array.isArray(state._tt_blocks_draft)) {
    state._tt_blocks_draft = getUserTimetableBlocks(u);
  }
  const synced = syncLegacyFromBlocks(state._tt_blocks_draft);
  state._tt_draft = synced.timetable;
  state._tt_names_draft = synced.timetable_names;
}

function openTimetableAddSheet(day, startMin) {
  ensureTimetableDrafts();
  const sm = Math.max(540, Math.min(1170, Number(startMin) || 540));
  const em = Math.min(1200, sm + 60);
  state._tt_sheet = {
    mode: "add",
    blockIdx: -1,
    day,
    start_min: sm,
    end_min: em,
    name: ""
  };
  render();
  setTimeout(() => {
    const inp = document.getElementById("tt-sheet-name-input");
    if (inp) inp.focus();
  }, 30);
}

function openTimetableEditSheet(blockIdx) {
  ensureTimetableDrafts();
  const idx = Number(blockIdx);
  const blk = state._tt_blocks_draft && state._tt_blocks_draft[idx];
  if (!blk) return;
  state._tt_sheet = {
    mode: "edit",
    blockIdx: idx,
    day: blk.day,
    start_min: Number(blk.start_min),
    end_min: Number(blk.end_min),
    name: blk.name || ""
  };
  render();
  setTimeout(() => {
    const inp = document.getElementById("tt-sheet-name-input");
    if (inp) inp.focus();
  }, 30);
}

function closeTimetableSheet() {
  state._tt_sheet = null;
  render();
}

function updateTimetableSheetTime(field, val) {
  if (!state._tt_sheet) return;
  const inp = document.getElementById("tt-sheet-name-input");
  if (inp) state._tt_sheet.name = inp.value;
  const num = Number(val);
  if (isNaN(num)) return;
  if (field === "start_min") {
    state._tt_sheet.start_min = num;
    if (state._tt_sheet.end_min <= num) {
      state._tt_sheet.end_min = Math.min(1200, num + 30);
    }
  } else if (field === "end_min") {
    state._tt_sheet.end_min = Math.max(state._tt_sheet.start_min + 30, num);
  }
  render();
}

function submitTimetableSheet() {
  if (!state._tt_sheet) return;
  ensureTimetableDrafts();
  const sheet = state._tt_sheet;
  const inp = document.getElementById("tt-sheet-name-input");
  const cleanName = String(inp ? inp.value : sheet.name || "").trim().slice(0, 60);
  const sm = Math.max(540, Math.min(1170, Number(sheet.start_min) || 540));
  const em = Math.max(sm + 30, Math.min(1200, Number(sheet.end_min) || (sm + 60)));

  // 같은 요일에 겹치는 기존 블록 제거 후 새 블록 반영
  const nextBlocks = (state._tt_blocks_draft || []).filter((b, i) => {
    if (sheet.mode === "edit" && i === sheet.blockIdx) return false;
    if (b.day !== sheet.day) return true;
    return b.end_min <= sm || b.start_min >= em;
  });
  nextBlocks.push({ day: sheet.day, name: cleanName, start_min: sm, end_min: em });
  state._tt_blocks_draft = nextBlocks;
  const synced = syncLegacyFromBlocks(nextBlocks);
  state._tt_draft = synced.timetable;
  state._tt_names_draft = synced.timetable_names;
  state._tt_sheet = null;
  render();
}

function deleteTimetableSheetSlots() {
  if (!state._tt_sheet) return;
  ensureTimetableDrafts();
  const idx = state._tt_sheet.blockIdx;
  if (idx >= 0) {
    state._tt_blocks_draft = (state._tt_blocks_draft || []).filter((_, i) => i !== idx);
    const synced = syncLegacyFromBlocks(state._tt_blocks_draft);
    state._tt_draft = synced.timetable;
    state._tt_names_draft = synced.timetable_names;
  }
  state._tt_sheet = null;
  render();
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
    const dataUrl = await compressTimetableImageToBase64(file, 960, 0.82);
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
    state._tt_blocks_draft = Array.isArray(data.timetable_blocks) && data.timetable_blocks.length
      ? data.timetable_blocks
      : buildBlocksFromLegacy(data.timetable || {}, data.timetable_names || {});
    const synced = syncLegacyFromBlocks(state._tt_blocks_draft);
    state._tt_draft = synced.timetable;
    state._tt_names_draft = synced.timetable_names;
    state._tt_sheet = null;
    state.timetable_tab = "edit";
    render();
    showToast(`AI가 수업 ${state._tt_blocks_draft.length}개를 자동으로 채웠어요! 확인 후 [시간표 저장]을 눌러주세요.`);
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
  state._tt_blocks_draft = [];
  state._tt_draft = { "월": [], "화": [], "수": [], "목": [], "금": [] };
  state._tt_names_draft = {};
  state._tt_sheet = null;
  render();
  showToast("시간표를 초기화했어요.");
}

function saveUserTimetable() {
  const u = DB.users[state.user_id];
  if (!u) return;
  const blocks = Array.isArray(state._tt_blocks_draft) ? state._tt_blocks_draft : getUserTimetableBlocks(u);
  const synced = syncLegacyFromBlocks(blocks);
  u.timetable_blocks = JSON.parse(JSON.stringify(blocks));
  u.timetable = synced.timetable;
  u.timetable_names = synced.timetable_names;
  u.timetable_saved = true;
  u.updated_at = Date.now();
  saveDB(true);
  state._tt_blocks_draft = null;
  state._tt_draft = null;
  state._tt_names_draft = null;
  state._tt_sheet = null;
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

function getMateAvatarEmoji(temp) {
  const t = Number(temp || 36.5);
  if (t >= 38.0) return "🦦";
  if (t >= 37.0) return "🐳";
  return "🐣";
}

function renderTimetableModal() {
  const u = DB.users[state.user_id];
  if (!u) return "";
  const pcMode = isPC();
  const curTab = state.timetable_tab || "mates";
  const blocks = Array.isArray(state._tt_blocks_draft) ? state._tt_blocks_draft : getUserTimetableBlocks(u);
  const syncedDraft = syncLegacyFromBlocks(blocks);
  const draft = syncedDraft.timetable;
  const hasSaved = hasUserTimetable(state.user_id);
  const mates = hasSaved ? getGonggangMates() : [];
  const colorMap = buildCourseColorMapFromBlocks(blocks);
  const sheet = state._tt_sheet || null;

  const todayDayRaw = getDayLabelFromDateStr(getTodayStr());
  const todayIdx = TT_DAYS.indexOf(todayDayRaw);
  const timelineDay = todayIdx >= 0 ? todayDayRaw : "월";
  const savedOrDraft = hasSaved ? (u.timetable || draft) : draft;
  const todayBusySet = new Set(Array.isArray(savedOrDraft[timelineDay]) ? savedOrDraft[timelineDay].map(Number) : []);
  const todayFreeCount = TT_PERIODS.filter(p => !todayBusySet.has(p)).length;
  const totalWeeklyMins = blocks.reduce((acc, b) => acc + Math.max(30, (Number(b.end_min) - Number(b.start_min)) || 60), 0);
  const totalWeeklyHoursLabel = totalWeeklyMins % 60 === 0 ? `${totalWeeklyMins / 60}시간` : `${(totalWeeklyMins / 60).toFixed(1)}시간`;

  const lockSvg = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#8B95A1" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`;
  const cameraSvg = (strokeColor) => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${strokeColor}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>`;
  const chevronRightSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#287D62" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M9 18l6-6-6-6"/></svg>`;
  const calendarSvg = `<svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="#287D62" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="3"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`;

  const dayHeadersHtml = TT_DAYS.map((d, di) => {
    const isToday = di === todayIdx;
    const label = isToday ? (pcMode ? `${d} · 오늘` : d) : d;
    return `<div class="tt-et-day" style="grid-column:${di + 2}; grid-row:1;">${isToday ? `<span class="tt-et-day-pill">${label}</span>` : label}</div>`;
  }).join("");

  const todayColBgHtml = todayIdx >= 0
    ? `<div class="tt-et-today-col" style="grid-column:${todayIdx + 2};"></div>`
    : "";

  const hourAxisHtml = TT_PERIODS.map((p, idx) =>
    `<div class="tt-et-hour" style="grid-row:${idx * 2 + 2} / span 2;">${periodToEverytimeHour(p)}${pcMode ? '시' : ''}</div>`
  ).join("");

  // 22개 30분 단위 빈 셀 (09:00 ~ 20:00)
  const emptyCellsHtml = TT_DAYS.map((d, di) => {
    const col = di + 2;
    let html = "";
    for (let s = 0; s < 22; s++) {
      const slotMin = 540 + s * 30;
      const row = s + 2;
      const isHalf = s % 2 === 1;
      const isAdding = Boolean(sheet && sheet.mode === "add" && sheet.day === d && sheet.start_min === slotMin);
      html += `<button type="button" class="tt-et-empty ${isHalf ? 'half' : ''} ${isAdding ? 'adding' : ''}" style="grid-column:${col}; grid-row:${row};" onclick="openTimetableAddSheet('${d}', ${slotMin})" aria-label="${d} ${minToHHMM(slotMin)} 추가">${isAdding ? '+' : ''}</button>`;
    }
    return html;
  }).join("");

  // 30분 단위 정밀 수업 블록
  const blockCellsHtml = blocks.map((b, bi) => {
    const di = TT_DAYS.indexOf(b.day);
    if (di < 0) return "";
    const col = di + 2;
    const sm = Math.max(540, Math.min(1170, Number(b.start_min) || 540));
    const em = Math.max(sm + 30, Math.min(1200, Number(b.end_min) || (sm + 60)));
    const rowStart = Math.round((sm - 540) / 30) + 2;
    const rowEnd = Math.round((em - 540) / 30) + 2;
    const pal = (b.name && colorMap[b.name]) ? colorMap[b.name] : TT_COURSE_PALETTE[1];
    const isSelected = Boolean(sheet && sheet.mode === "edit" && sheet.blockIdx === bi);
    return `
      <button type="button" class="tt-et-block ${isSelected ? 'selected' : ''}"
        style="grid-column:${col}; grid-row:${rowStart} / ${rowEnd}; background:${pal.bg}; color:${pal.text};"
        onclick="openTimetableEditSheet(${bi})">
        <span class="tt-et-block-name">${escHtml(b.name || "수업")}</span>
        ${pcMode ? `<span class="tt-et-block-time">${minToHHMM(sm)}–${minToHHMM(em)}</span>` : ''}
      </button>
    `;
  }).join("");

  const editorHtml = `
    <div class="tt-v3-card">
      ${pcMode ? `
        <div class="tt-v3-card-head">
          <div>
            <div style="font-size:17px; font-weight:800; color:#191F28;">내 시간표</div>
            <div class="tt-v3-hint-line" style="margin:4px 0 0;">주 ${totalWeeklyHoursLabel} 수업 · 30분 단위로 칸을 눌러 추가·수정</div>
          </div>
          <button type="button" class="tt-v3-reset-btn" onclick="resetTimetableDraft()">초기화</button>
        </div>
      ` : ''}

      <button type="button" class="tt-v3-ai-banner" onclick="triggerTimetableImageUpload()" ${state._tt_ai_loading ? 'disabled' : ''}>
        <span class="tt-v3-ai-ic">${cameraSvg("#287D62")}</span>
        <span class="tt-v3-ai-copy">
          <span class="tt-v3-ai-title">${state._tt_ai_loading ? 'AI가 시간표를 분석하고 있어요...' : '사진 한 장으로 자동 채우기'}</span>
          <span class="tt-v3-ai-sub">${pcMode ? '에브리타임·포털 캡처를 올리면 칸이 채워져요 · 사진은 저장 안 해요' : '에브리타임·포털 캡처 · 사진은 저장 안 해요'}</span>
        </span>
        ${pcMode
          ? `<span class="tt-v3-ai-cta">${state._tt_ai_loading ? '분석중' : '업로드'}</span>`
          : chevronRightSvg}
      </button>

      ${!pcMode ? `<div class="tt-v3-hint-line">빈 칸을 눌러 30분 단위로 추가 · 주 ${totalWeeklyHoursLabel} 수업</div>` : ''}

      <div class="tt-et-wrap">
        <div class="tt-et-grid">
          <div class="tt-et-corner"></div>
          ${dayHeadersHtml}
          ${todayColBgHtml}
          ${hourAxisHtml}
          ${emptyCellsHtml}
          ${blockCellsHtml}
        </div>
      </div>

      ${pcMode ? `<button type="button" class="tt-v3-save-btn" onclick="saveUserTimetable()">시간표 저장</button>` : ''}
    </div>
  `;

  const todayTimelineHtml = `
    <div class="${pcMode ? '' : 'tt-v3-today-box'}">
      <div class="tt-v3-today-label">${todayIdx >= 0 ? `오늘(${timelineDay}) 내 공강` : `${timelineDay}요일 내 공강`}</div>
      <div class="tt-v3-today-count">${todayFreeCount}시간 비어 있어요</div>
      <div class="tt-v3-timeline-bars">
        ${TT_PERIODS.map(p => `<div class="tt-v3-tbar ${todayBusySet.has(p) ? '' : 'free'}" title="${periodToEverytimeHour(p)}시 ${todayBusySet.has(p) ? '수업' : '공강'}"></div>`).join("")}
      </div>
      <div class="tt-v3-timeline-ticks">
        <span>9</span>
        <span>12</span>
        <span>3</span>
        <span>6</span>
        <span>7</span>
      </div>
    </div>
  `;

  const mateCardsHtml = mates.length === 0 ? `
    <div style="text-align:center; padding:28px 16px; background:#F7F8FA; border-radius:18px;">
      <div style="font-size:14.5px; font-weight:800; color:#191F28; margin-bottom:6px;">아직 공강이 겹치는 학우가 없어요</div>
      <div style="font-size:12.5px; color:#6B7684; margin-bottom:14px;">먼저 내 공강 시간에 맞춰 번개를 열어보는 건 어떨까요?</div>
      <button type="button" onclick="state.active_modal='create'; render();" style="height:38px; padding:0 18px; border-radius:12px; border:none; background:#287D62; color:#FFFFFF; font-size:13px; font-weight:800; cursor:pointer;">내 공강에 번개 열기</button>
    </div>
  ` : `
    <div class="tt-v3-mate-list">
      ${mates.map(m => {
        const tier = getTierByTemp(m.user.manner_temp || 36.5);
        const broadDept = typeof getBroadCollege === "function" ? getBroadCollege(m.user.department) : (m.user.department || "울산대");
        const avEmoji = getMateAvatarEmoji(m.user.manner_temp);
        const pct = Math.max(5, Math.min(100, Number(m.overlap.pct || 0)));
        return `
          <div class="tt-v3-mate-card">
            <div class="tt-v3-mate-top">
              <div class="tt-v3-mate-av">${avEmoji}</div>
              <div style="min-width:0; flex:1;">
                <div class="tt-v3-mate-name">${escHtml(tier.name)} · ${tier.displayTemp}°C</div>
                <div class="tt-v3-mate-dept">${escHtml(broadDept)}</div>
              </div>
            </div>
            <div class="tt-v3-mate-hl">${escHtml(m.overlap.highlightText)}</div>
            <div class="tt-v3-mate-foot">
              <div class="tt-v3-mate-prog-wrap">
                <div class="tt-v3-mate-hours">주 ${m.overlap.overlapHours}시간 겹쳐요</div>
                <div class="tt-v3-mate-bar-row">
                  <div class="tt-v3-mate-bar-track"><div class="tt-v3-mate-bar-fill" style="width:${pct}%;"></div></div>
                  <span class="tt-v3-mate-pct">${pct}%</span>
                </div>
              </div>
              <button type="button" class="tt-v3-mate-cta" onclick="inviteGonggangMate('${m.uid}', '${m.overlap.bestMeetDate}', '${m.overlap.bestMeetTime}')">번개 열기</button>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;

  const emptyStateHtml = `
    <div class="tt-v3-empty-state">
      <div class="tt-v3-empty-ic">${calendarSvg}</div>
      <h2 class="tt-v3-empty-title">시간표를 넣으면<br>공강 메이트를 찾아드려요</h2>
      <p class="tt-v3-empty-sub">${pcMode ? '왼쪽에서 시간표를 입력하고 저장하면 공강이 겹치는 학우가 여기에 표시돼요' : '공강이 겹치는 학우와 바로 밥약·카공 번개를 열 수 있어요'}</p>
      ${!pcMode ? `
        <div class="tt-v3-empty-privacy">${lockSvg}<span>사진은 분석 후 바로 지워져요</span></div>
        <button type="button" class="tt-v3-empty-btn-primary" onclick="triggerTimetableImageUpload()" ${state._tt_ai_loading ? 'disabled' : ''}>
          ${cameraSvg("#FFFFFF")}
          <span>${state._tt_ai_loading ? 'AI가 시간표를 분석하고 있어요...' : '사진으로 자동 채우기'}</span>
        </button>
        <button type="button" class="tt-v3-empty-btn-secondary" onclick="ensureTimetableDrafts(); state.timetable_tab='edit'; render();">직접 입력할게요</button>
      ` : ''}
    </div>
  `;

  const matesSectionHtml = !hasSaved ? emptyStateHtml : (pcMode ? `
    <div class="tt-v3-card tt-v3-pc-mates-card">
      ${todayTimelineHtml}
      <div style="height:1px; background:#F2F4F6; margin:16px 0;"></div>
      <div class="tt-v3-mates-head">공강이 겹치는 학우 ${mates.length}명</div>
      <div class="tt-v3-privacy-row">${lockSvg}<span>단과대·매너온도만 보여요</span></div>
      ${mateCardsHtml}
    </div>
  ` : `
    <div>
      ${todayTimelineHtml}
      <div class="tt-v3-mates-head">공강이 겹치는 학우 ${mates.length}명</div>
      <div class="tt-v3-privacy-row">${lockSvg}<span>단과대와 매너온도만 보여요 · 이름·학번은 수락 전까지 비밀</span></div>
      ${mateCardsHtml}
    </div>
  `);

  let sheetHtml = "";
  if (sheet) {
    const startOpts = [];
    for (let m = 540; m <= 1170; m += 30) {
      startOpts.push(`<option value="${m}" ${sheet.start_min === m ? 'selected' : ''}>${minToHHMM(m)} (${minToKoreanLabel(m)})</option>`);
    }
    const endOpts = [];
    for (let m = sheet.start_min + 30; m <= 1200; m += 30) {
      endOpts.push(`<option value="${m}" ${sheet.end_min === m ? 'selected' : ''}>${minToHHMM(m)} (${minToKoreanLabel(m)})</option>`);
    }
    const titleStr = `${sheet.day}요일 수업 ${sheet.mode === "edit" ? '수정' : '추가'}`;
    const subStr = `${minToHHMM(sheet.start_min)} – ${minToHHMM(sheet.end_min)}`;
    sheetHtml = `
      <div class="tt-v3-sheet-backdrop" onclick="if(event.target===this) closeTimetableSheet();">
        <div class="tt-v3-sheet" onclick="event.stopPropagation();">
          <div class="tt-v3-sheet-handle"></div>
          <h3 class="tt-v3-sheet-title">${escHtml(titleStr)}</h3>
          <p class="tt-v3-sheet-sub">${escHtml(subStr)}</p>
          <div class="tt-v3-input-box">
            <input id="tt-sheet-name-input" type="text" maxlength="60" value="${escHtml(sheet.name || '')}" placeholder="수업명 입력 (예: ICT융합개론)" onkeydown="if(event.key==='Enter'){event.preventDefault(); submitTimetableSheet();}" />
          </div>
          <p class="tt-v3-sheet-note">수업명은 나만 보여요 · 30분 단위로 시작·종료 시간을 고를 수 있어요</p>
          <div class="tt-v3-time-row">
            <select class="tt-v3-time-select" aria-label="시작 시간" onchange="updateTimetableSheetTime('start_min', this.value)">
              ${startOpts.join("")}
            </select>
            <span style="font-weight:800; color:#8B95A1;">~</span>
            <select class="tt-v3-time-select" aria-label="종료 시간" onchange="updateTimetableSheetTime('end_min', this.value)">
              ${endOpts.join("")}
            </select>
          </div>
          <div class="tt-v3-sheet-actions">
            ${sheet.mode === "edit"
              ? `<button type="button" class="tt-v3-btn-del" onclick="deleteTimetableSheetSlots()">삭제</button>`
              : `<button type="button" class="tt-v3-btn-cancel" onclick="closeTimetableSheet()">취소</button>`}
            <button type="button" class="tt-v3-btn-submit" onclick="submitTimetableSheet()">${sheet.mode === "edit" ? '수정하기' : '추가하기'}</button>
          </div>
        </div>
      </div>
    `;
  }

  return `
    <div class="tt-v3-page">
      <input id="tt-image-upload-input" type="file" accept="image/*" style="display:none;" onchange="handleTimetableImageUpload(this)" />
      <div class="tt-v3-topbar">
        <div class="tt-v3-topbar-left">
          <button type="button" class="v3-back-btn" onclick="closeTimetableModal()" aria-label="뒤로 가기"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#191F28" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg></button>
          <h1 class="tt-v3-title">시간표</h1>
        </div>
        ${!pcMode && curTab === "edit" ? `<button type="button" class="tt-v3-reset-btn" onclick="resetTimetableDraft()">초기화</button>` : ''}
      </div>

      ${pcMode ? `
        <div class="pc-tt-2col">
          ${editorHtml}
          ${matesSectionHtml}
        </div>
      ` : `
        <div class="tt-v3-seg" role="tablist">
          <button type="button" class="tt-v3-seg-btn ${curTab === 'mates' ? 'active' : ''}" onclick="state.timetable_tab='mates'; render();">공강 메이트${hasSaved ? ` ${mates.length}` : ''}</button>
          <button type="button" class="tt-v3-seg-btn ${curTab === 'edit' ? 'active' : ''}" onclick="ensureTimetableDrafts(); state.timetable_tab='edit'; render();">내 시간표</button>
        </div>
        ${curTab === 'edit' ? editorHtml : matesSectionHtml}
        ${curTab === 'edit' ? `
          <div class="tt-v3-sticky-save">
            <button type="button" class="tt-v3-save-btn" onclick="saveUserTimetable()">시간표 저장</button>
          </div>
        ` : ''}
      `}
      ${sheetHtml}
    </div>
  `;
}
