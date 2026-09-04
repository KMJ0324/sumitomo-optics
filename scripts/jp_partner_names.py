"""UN M49 numeric area code -> Korean name, for UN Comtrade partner rows.

Comtrade's keyless preview endpoint returns `partnerCode` but leaves
`partnerDesc` null, so the destination table needs its own lookup. This
covers the areas that realistically show up in Japan's optical-product
exports; anything unmapped falls back to "M49 <code>" rather than being
dropped, so an unexpected destination is still visible and countable.

Comtrade quirks worth knowing when reading the table:
  - 0 is the World aggregate, not a country.
  - Taiwan is reported as 490 "Other Asia, nes".
  - Several countries are reported under Comtrade's own extended codes
    rather than the plain M49 one - the US as 842 (with Puerto Rico and the
    US Virgin Islands) rather than 840, France as 251, Switzerland as 757,
    Norway as 579. Both spellings are mapped so the table names the
    destination whichever code the response happens to carry.
"""

PARTNER_NAMES = {
    0: "전세계",
    12: "알제리", 32: "아르헨티나", 36: "호주", 40: "오스트리아", 48: "바레인",
    50: "방글라데시", 56: "벨기에", 68: "볼리비아", 76: "브라질", 96: "브루나이",
    100: "불가리아", 104: "미얀마", 112: "벨라루스", 116: "캄보디아", 124: "캐나다",
    144: "스리랑카", 152: "칠레", 156: "중국", 170: "콜롬비아", 188: "코스타리카",
    191: "크로아티아", 196: "키프로스", 203: "체코", 208: "덴마크", 218: "에콰도르",
    222: "엘살바도르", 231: "에티오피아", 233: "에스토니아", 242: "피지", 246: "핀란드",
    250: "프랑스", 268: "조지아", 275: "팔레스타인", 276: "독일", 288: "가나",
    300: "그리스", 320: "과테말라", 344: "홍콩", 348: "헝가리", 356: "인도",
    360: "인도네시아", 364: "이란", 368: "이라크", 372: "아일랜드", 376: "이스라엘",
    380: "이탈리아", 384: "코트디부아르", 388: "자메이카", 392: "일본", 398: "카자흐스탄",
    400: "요르단", 404: "케냐", 410: "한국", 414: "쿠웨이트", 417: "키르기스스탄",
    418: "라오스", 422: "레바논", 428: "라트비아", 440: "리투아니아", 442: "룩셈부르크",
    458: "말레이시아", 462: "몰디브", 484: "멕시코", 490: "대만(기타 아시아)",
    496: "몽골", 504: "모로코", 512: "오만", 524: "네팔", 528: "네덜란드",
    554: "뉴질랜드", 558: "니카라과", 566: "나이지리아", 578: "노르웨이", 586: "파키스탄",
    591: "파나마", 600: "파라과이", 604: "페루", 608: "필리핀", 616: "폴란드",
    620: "포르투갈", 634: "카타르", 642: "루마니아", 643: "러시아", 682: "사우디아라비아",
    699: "인도(구)", 702: "싱가포르", 703: "슬로바키아", 704: "베트남", 705: "슬로베니아",
    710: "남아프리카공화국", 724: "스페인", 748: "에스와티니", 752: "스웨덴", 756: "스위스",
    760: "시리아", 762: "타지키스탄", 764: "태국", 784: "아랍에미리트", 788: "튀니지",
    792: "튀르키예", 795: "투르크메니스탄", 800: "우간다", 804: "우크라이나", 818: "이집트",
    826: "영국", 834: "탄자니아", 840: "미국", 858: "우루과이", 860: "우즈베키스탄",
    862: "베네수엘라", 887: "예멘", 894: "잠비아",

    # Comtrade 확장 코드 (같은 나라를 M49 코드 대신 이 번호로 보고합니다)
    58: "벨기에·룩셈부르크", 251: "프랑스", 381: "이탈리아", 446: "마카오",
    579: "노르웨이", 699: "인도", 757: "스위스", 842: "미국", 882: "사모아",
}


def partner_name(code) -> str:
    try:
        return PARTNER_NAMES.get(int(code), f"M49 {code}")
    except (TypeError, ValueError):
        return f"M49 {code}"
