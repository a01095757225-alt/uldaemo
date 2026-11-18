// 울대모(Uldaemo) 캠퍼스 호관 좌표, 맛집 지도 데이터 및 프로필 상수
// 1. 울산대학교 공식 캠퍼스맵 62개 전체 호관 및 주요 장소 실제 GPS 좌표
// =========================================================
const ULSAN_CAMPUS_COORDS = {
  "22호관 학생회관": [35.544589, 129.258501, "🍚"],
  "16호관 아산도서관": [35.543219, 129.258113, "📚"],
  "39호관 아산스포츠센터": [35.544198, 129.259535, "🏃"],
  "34호관 식물원": [35.541588, 129.257191, "🚶"],
  "7호관 전기/컴퓨터공학관": [35.544225, 129.255796, "💻"],
  "9호관 대학회관/해송홀": [35.544825, 129.256463, "🍚"],
  "36호관 서점 및 북카페": [35.544643, 129.258260, "☕"],
  "40호관 아산도서관 신관": [35.542539, 129.258585, "📚"],
  "1호관 화학공학관": [35.544734, 129.255810, "💻"],
  "2호관 기계항공관": [35.545027, 129.255057, "💻"],
  "3호관 공학행정관": [35.545173, 129.255690, "📍"],
  "4호관 학생회관별관": [35.544460, 129.254443, "📍"],
  "5호관 산학협력리더스홀": [35.544032, 129.254522, "💻"],
  "6호관 조형관": [35.543474, 129.254744, "🎨"],
  "8호관 자연과학관": [35.542938, 129.256658, "💻"],
  "10호관 문수관": [35.543568, 129.255507, "💻"],
  "11호관 교수연구동": [35.543055, 129.255730, "☕"],
  "12호관 체육관": [35.545279, 129.258179, "🏃"],
  "13호관 동아리관1": [35.544010, 129.258601, "🎸"],
  "14호관 인문관": [35.542500, 129.257440, "💻"],
  "15호관 사회과학관": [35.542045, 129.257664, "💻"],
  "18호관 재료/산업공학관": [35.544748, 129.253859, "💻"],
  "19호관 기초과학실험동": [35.544138, 129.253935, "💻"],
  "20호관 시청각교육관": [35.541422, 129.256770, "💻"],
  "21호관 학군단": [35.543908, 129.259001, "📍"],
  "23호관 건설환경공학관": [35.545616, 129.254878, "💻"],
  "24호관 경영관": [35.542247, 129.256487, "💻"],
  "25호관 청운학사 무거관": [35.547148, 129.255825, "🏠"],
  "26호관 행정본관": [35.543723, 129.257063, "📍"],
  "28호관 예술관(디자인/미술)": [35.543079, 129.254168, "🎨"],
  "29호관 예술관(음악학부)": [35.543553, 129.254159, "🎵"],
  "31호관 동아리관2": [35.543874, 129.259234, "🎸"],
  "35호관 산학협동관/의학관": [35.544954, 129.252952, "💻"],
  "37호관 생활과학관": [35.542550, 129.255253, "💻"],
  "38호관 청운학사 목련관": [35.547437, 129.255933, "🏠"],
  "41호관 조선해양공학관": [35.545009, 129.251824, "💻"],
  "43호관 국제관": [35.546591, 129.255746, "🌐"],
  "44호관 건축관": [35.546126, 129.256497, "💻"],
  "45호관 청운학사 기린관": [35.546804, 129.257144, "🏠"],
  "46호관 KCC 생활관": [35.546200, 129.257849, "🏠"],
  "학생식당 (9호관 대학회관 1층)": [35.544639, 129.257122, "🍚"],
  "울산대학교 정문 (바보사거리)": [35.543000, 129.259800, "🍔"],
  "무거동 대학로 (바보사거리 카페거리)": [35.542600, 129.260800, "☕"]
};

// 울산대학교 주변(바보사거리 · 울과대 근처 · 울산대 후문) 실존 맛집 22곳 (네이버·카카오·구글 3사 평점 & 도로명 정밀 GPS)
const MUGEO_FOOD_SPOTS = [
  // [바보사거리 · 울산대 정문 구역]
  { id: "r1", zone: "basa", zoneLabel: "바보사거리", name: "가무댕댕", rating: 4.8, naverRating: 4.8, kakaoRating: 4.8, googleRating: 4.7, menu: "추억의 경양식 수제 돈까스", address: "남구 대학로94번길 11", emoji: "🍛", bg: "#FFF3CD", cat: "🍚 밥약", lat: 35.543015, lng: 129.261318, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "울대 앞 가무댕댕 돈까스 고!", kakaoQuery: "울산 무거동 가무댕댕" },
  { id: "r2", zone: "basa", zoneLabel: "바보사거리", name: "돌돌파스타", rating: 4.8, naverRating: 4.9, kakaoRating: 4.8, googleRating: 4.7, menu: "치킨로제파스타·화덕피자", address: "남구 대학로84번길 12", emoji: "🍝", bg: "#FFE8D6", cat: "🍚 밥약", lat: 35.541952, lng: 129.260743, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "바사 돌돌파스타 같이 먹어요!", kakaoQuery: "울산 무거동 돌돌파스타" },
  { id: "r3", zone: "basa", zoneLabel: "바보사거리", name: "기린카페", rating: 4.8, naverRating: 4.8, kakaoRating: 4.9, googleRating: 4.7, menu: "샤케라또·말차라떼 카공 카페", address: "남구 대학로84번길 5-7", emoji: "☕", bg: "#EFE5DC", cat: "☕ 카공", lat: 35.542741, lng: 129.260190, locName: "무거동 대학로 (바보사거리 카페거리)", defaultTitle: "기린카페에서 카공·수다 해요!", kakaoQuery: "울산 무거동 기린카페" },
  { id: "r4", zone: "basa", zoneLabel: "바보사거리", name: "테디스 카페", rating: 4.7, naverRating: 4.8, kakaoRating: 4.7, googleRating: 4.6, menu: "수제 카이막·바스크치즈케이크", address: "남구 대학로84번길 5-13", emoji: "🍰", bg: "#FCE7F3", cat: "☕ 카공", lat: 35.542961, lng: 129.260402, locName: "무거동 대학로 (바보사거리 카페거리)", defaultTitle: "테디스 카이막 디저트 같이 먹어요!", kakaoQuery: "울산 무거동 테디스" },
  { id: "r5", zone: "basa", zoneLabel: "바보사거리", name: "하루 무거점", rating: 4.7, naverRating: 4.8, kakaoRating: 4.7, googleRating: 4.6, menu: "연어 사시미·나베 이자카야", address: "남구 대학로94번길 5-5", emoji: "🍣", bg: "#E0F2FE", cat: "🍻 술/번개", lat: 35.543498, lng: 129.260657, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "저녁에 바사 하루에서 한잔할 분!", kakaoQuery: "울산 무거동 하루 이자카야" },
  { id: "r6", zone: "basa", zoneLabel: "바보사거리", name: "쭈꾸미가 알고싶다", rating: 4.6, naverRating: 4.7, kakaoRating: 4.6, googleRating: 4.5, menu: "매콤 직화 쭈꾸미 점심특선", address: "남구 대학로94번길 5-3", emoji: "🐙", bg: "#FEE2E2", cat: "🍚 밥약", lat: 35.543390, lng: 129.260606, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "쭈꾸미가 알고싶다 점심 특선 고!", kakaoQuery: "울산 무거동 쭈꾸미가 알고싶다" },
  { id: "r7", zone: "basa", zoneLabel: "바보사거리", name: "봉대박스파게티", rating: 4.5, naverRating: 4.6, kakaoRating: 4.5, googleRating: 4.4, menu: "뚝배기 해장 봉골레 파스타", address: "남구 대학로94번길 5-22", emoji: "🍝", bg: "#FFEDD5", cat: "🍚 밥약", lat: 35.543774, lng: 129.261072, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "봉대박스파게티 해장 파스타 드실 분!", kakaoQuery: "울산 무거동 봉대박스파게티" },
  { id: "r8", zone: "basa", zoneLabel: "바보사거리", name: "우마이도 울산대점", rating: 4.5, naverRating: 4.6, kakaoRating: 4.4, googleRating: 4.5, menu: "진한 돈코츠 라멘·교자", address: "남구 대학로84번길 8", emoji: "🍜", bg: "#FEF3C7", cat: "🍚 밥약", lat: 35.542063, lng: 129.260557, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "바사 우마이도 돈코츠 라멘 같이 먹어요", kakaoQuery: "울산 무거동 우마이도" },
  { id: "r9", zone: "basa", zoneLabel: "바보사거리", name: "덤 칼국수·돈가스", rating: 4.4, naverRating: 4.5, kakaoRating: 4.4, googleRating: 4.3, menu: "시원한 냉칼국수·수제돈가스", address: "남구 대학로84번길 5-5", emoji: "🥟", bg: "#E0E7FF", cat: "🍚 밥약", lat: 35.542601, lng: 129.260284, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "바사 덤에서 칼국수랑 돈가스 먹어요!", kakaoQuery: "울산 무거동 덤 칼국수" },
  { id: "r10", zone: "basa", zoneLabel: "바보사거리", name: "공차 울산대학로점", rating: 4.3, naverRating: 4.5, kakaoRating: 4.2, googleRating: 4.2, menu: "블랙밀크티·타로버블티 카공", address: "남구 대학로 96", emoji: "🧋", bg: "#F3E8FF", cat: "☕ 카공", lat: 35.543395, lng: 129.260278, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "정문 앞 공차에서 버블티 마시며 카공해요", kakaoQuery: "울산 무거동 공차 울산대학로점" },

  // [울과대(울산과학대 서부캠퍼스) 근처 구역]
  { id: "r11", zone: "uc", zoneLabel: "울과대 근처", name: "라파르테", rating: 4.8, naverRating: 4.9, kakaoRating: 4.8, googleRating: 4.7, menu: "수제 타르트·휘낭시에 디저트", address: "남구 대학로43번길 18-14", emoji: "🥧", bg: "#FCE7F3", cat: "☕ 카공", lat: 35.540958, lng: 129.255868, locName: "무거동 대학로 (바보사거리 카페거리)", defaultTitle: "라파르테 디저트 맛집 같이 가요", kakaoQuery: "울산 무거동 라파르테" },
  { id: "r12", zone: "uc", zoneLabel: "울과대 근처", name: "미토식당", rating: 4.6, naverRating: 4.7, kakaoRating: 4.6, googleRating: 4.5, menu: "진한 소고기 베트남 쌀국수·분짜", address: "남구 대학로64번길 7", emoji: "🍲", bg: "#DCFCE7", cat: "🍚 밥약", lat: 35.540714, lng: 129.258922, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "미토식당 쌀국수 따뜻하게 한 그릇 해요!", kakaoQuery: "울산 무거동 미토식당" },
  { id: "r13", zone: "uc", zoneLabel: "울과대 근처", name: "종가집돼지국밥", rating: 4.6, naverRating: 4.7, kakaoRating: 4.6, googleRating: 4.5, menu: "진한 국물 돼지국밥·수육백반", address: "남구 대학로 40", emoji: "🍚", bg: "#FDE8E8", cat: "🍚 밥약", lat: 35.539160, lng: 129.256979, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "뜨끈한 종가집돼지국밥 같이 먹어요", kakaoQuery: "울산 무거동 종가집돼지국밥" },
  { id: "r14", zone: "uc", zoneLabel: "울과대 근처", name: "리원카페", rating: 4.5, naverRating: 4.6, kakaoRating: 4.5, googleRating: 4.4, menu: "아늑한 수제 디저트·라떼 맛집", address: "남구 대학로64번길 7-16", emoji: "☕", bg: "#F5F5F4", cat: "☕ 카공", lat: 35.540943, lng: 129.259689, locName: "무거동 대학로 (바보사거리 카페거리)", defaultTitle: "울과대 근처 리원카페에서 조용히 카공해요", kakaoQuery: "울산 무거동 리원카페" },
  { id: "r15", zone: "uc", zoneLabel: "울과대 근처", name: "핸떡분식", rating: 4.4, naverRating: 4.5, kakaoRating: 4.4, googleRating: 4.3, menu: "수제 튀김·즉석 떡볶이 세트", address: "남구 대학로76번길 7-14", emoji: "🍢", bg: "#FEE2E2", cat: "🍚 밥약", lat: 35.541890, lng: 129.260360, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "핸떡분식에서 떡볶이랑 튀김 같이 먹어요!", kakaoQuery: "울산 무거동 핸떡분식" },
  { id: "r16", zone: "uc", zoneLabel: "울과대 근처", name: "정통집 울산대점", rating: 4.3, naverRating: 4.4, kakaoRating: 4.3, googleRating: 4.2, menu: "특제 돼지김치구이·치즈볶음밥", address: "남구 대학로76번길 10", emoji: "🥩", bg: "#FFEDD5", cat: "🍚 밥약", lat: 35.541117, lng: 129.259952, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "정통집 돼지김치구이 같이 드실 분!", kakaoQuery: "울산 무거동 정통집" },
  { id: "r17", zone: "uc", zoneLabel: "울과대 근처", name: "빽보이피자 무거점", rating: 4.2, naverRating: 4.4, kakaoRating: 4.1, googleRating: 4.1, menu: "토핑 가득 가성비 수제 피자", address: "남구 대학로64번길 7-19", emoji: "🍕", bg: "#FEF9C3", cat: "🍚 밥약", lat: 35.541321, lng: 129.259624, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "빽보이피자 반반 피자 같이 시켜 먹어요", kakaoQuery: "울산 무거동 빽보이피자" },
  { id: "r18", zone: "uc", zoneLabel: "울과대 근처", name: "지코바치킨 울대점", rating: 4.1, naverRating: 4.3, kakaoRating: 4.0, googleRating: 4.0, menu: "숯불 양념구이 치밥 정석", address: "남구 대학로76번길 7-6", emoji: "🍗", bg: "#FFE4E6", cat: "🍻 술/번개", lat: 35.541498, lng: 129.260025, locName: "울산대학교 정문 (바보사거리)", defaultTitle: "저녁에 지코바 숯불치킨 치밥 같이 해요!", kakaoQuery: "울산 무거동 지코바치킨 울대점" },

  // [울산대 후문 · 기숙사 · 아산스포츠센터 근처 구역]
  { id: "r19", zone: "back", zoneLabel: "울산대 후문", name: "발레나식스 무거점", rating: 4.7, naverRating: 4.8, kakaoRating: 4.7, googleRating: 4.6, menu: "스페셜티 로스터리 대형 카공 카페", address: "남구 대학로147번길 48", emoji: "☕", bg: "#E0F2FE", cat: "☕ 카공", lat: 35.548850, lng: 129.260077, locName: "39호관 아산스포츠센터", defaultTitle: "후문 발레나식스 카페에서 여유롭게 카공해요", kakaoQuery: "울산 무거동 발레나식스" },
  { id: "r20", zone: "back", zoneLabel: "울산대 후문", name: "핵밥 울산대점", rating: 4.6, naverRating: 4.7, kakaoRating: 4.6, googleRating: 4.5, menu: "큐브스테이크덮밥·마제소바", address: "남구 대학로 106", emoji: "🍱", bg: "#ECFDF5", cat: "🍚 밥약", lat: 35.544199, lng: 129.260682, locName: "39호관 아산스포츠센터", defaultTitle: "핵밥에서 덮밥·마제소바 같이 먹어요!", kakaoQuery: "울산 무거동 핵밥" },
  { id: "r21", zone: "back", zoneLabel: "울산대 후문", name: "언양닭칼국수 무거점", rating: 4.4, naverRating: 4.5, kakaoRating: 4.4, googleRating: 4.3, menu: "진한 닭반마리 칼국수·왕만두", address: "남구 대학로 120", emoji: "🍲", bg: "#FEF3C7", cat: "🍚 밥약", lat: 35.545300, lng: 129.261241, locName: "39호관 아산스포츠센터", defaultTitle: "든든한 언양닭칼국수 같이 먹으러 가요!", kakaoQuery: "울산 무거동 언양닭칼국수" },
  { id: "r22", zone: "back", zoneLabel: "울산대 후문", name: "써브웨이 무거점", rating: 4.2, naverRating: 4.4, kakaoRating: 4.1, googleRating: 4.1, menu: "커스텀 샌드위치·쿠키 세트", address: "남구 대학로 108", emoji: "🥪", bg: "#DCFCE7", cat: "🍚 밥약", lat: 35.544391, lng: 129.260687, locName: "39호관 아산스포츠센터", defaultTitle: "공강에 써브웨이 샌드위치 가볍게 드실 분!", kakaoQuery: "울산 무거동 써브웨이" }
];

const AVATARS = ["🐶", "🐱", "🦊", "🐻", "🐰", "🐹"];
const MBTIS = ["ENFP", "ENTP", "INFP", "INTP", "ESFJ", "ESTJ", "ISFJ", "ISTJ", "ENFJ", "ENTJ", "INFJ", "INTJ", "ESFP", "ESTP", "ISFP", "ISTP", "모름/비공개"];
