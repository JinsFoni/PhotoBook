"""演示种子数据 — 从静态设计稿 data.js 确定性生成(仅空库首启导入)。"""

MODELS = [
 {
  "slug": "yang-chenchen",
  "name": "Yang Chenchen",
  "stage": "",
  "featured": False,
  "avatar": "1529626455594-4ff0802cfb7e",
  "hero": "1529626455594-4ff0802cfb7e",
  "gender": "Female",
  "age": False,
  "height": "168 cm",
  "measurements": False,
  "agency": "ABC Agency",
  "tags": [
   "Fashion",
   "Portrait",
   "Editorial"
  ],
  "bio": "Shot between Shanghai and Lisbon, Chenchen's archive work moves between sharp tailoring and unstructured linen. She reads a room quickly and gives the camera very little, which is the point.",
  "since": "2024"
 },
 {
  "slug": "imogen-vale",
  "name": "Imogen Vale",
  "stage": "VALE",
  "featured": False,
  "avatar": "1494790108377-be9c29b29330",
  "hero": "1494790108377-be9c29b29330",
  "gender": "Female",
  "age": 27,
  "height": "174 cm",
  "measurements": "81-61-88",
  "agency": "Vale Management",
  "tags": [
   "Fashion",
   "Movement",
   "Studio"
  ],
  "bio": "London-based, trained in dance. Vale's frames are usually caught mid-movement, so the archive holds more outtakes than selects.",
  "since": "2023"
 },
 {
  "slug": "sora-nakamura",
  "name": "Sora Nakamura",
  "stage": "",
  "featured": False,
  "avatar": "1534528741775-53994a69daeb",
  "hero": "1534528741775-53994a69daeb",
  "gender": "Female",
  "age": False,
  "height": False,
  "measurements": False,
  "agency": False,
  "tags": [
   "Available Light",
   "Portrait"
  ],
  "bio": "Nakamura works almost exclusively in available light. The result is a body of work with an unusually narrow palette and an unusually wide range of expression.",
  "since": "2025"
 },
 {
  "slug": "mara-lindqvist",
  "name": "Mara Lindqvist",
  "stage": "",
  "featured": False,
  "avatar": "1517841905240-472988babdf9",
  "hero": "1517841905240-472988babdf9",
  "gender": "Female",
  "age": 31,
  "height": "179 cm",
  "measurements": False,
  "agency": "Nordisk",
  "tags": [
   "Editorial",
   "Studio",
   "Monochrome"
  ],
  "bio": "Stockholm. Lindqvist came to the archive from architecture photography, and it shows in the way she holds a line.",
  "since": "2022"
 },
 {
  "slug": "priya-raghavan",
  "name": "Priya Raghavan",
  "stage": "",
  "featured": False,
  "avatar": "1524504388940-b1c1722653e1",
  "hero": "1524504388940-b1c1722653e1",
  "gender": "Female",
  "age": 24,
  "height": "165 cm",
  "measurements": "84-63-89",
  "agency": False,
  "tags": [
   "Outdoor",
   "Fashion"
  ],
  "bio": "Mumbai. Raghavan's sittings run long and get quieter as they go; most of this archive is from the last hour.",
  "since": "2025"
 },
 {
  "slug": "camille-okonjo",
  "name": "Camille Okonjo",
  "stage": "",
  "featured": False,
  "avatar": "1502823403499-6ccfcf4fb453",
  "hero": "1502823403499-6ccfcf4fb453",
  "gender": "Female",
  "age": False,
  "height": "171 cm",
  "measurements": False,
  "agency": "Atelier 9",
  "tags": [
   "Outdoor",
   "Colour",
   "Editorial"
  ],
  "bio": "Lagos and Marseille. Okonjo shoots in colour almost exclusively, and almost always outdoors.",
  "since": "2024"
 },
 {
  "slug": "elias-brandt",
  "name": "Elias Brandt",
  "stage": "",
  "featured": False,
  "avatar": "1506794778202-cad84cf45f1d",
  "hero": "1506794778202-cad84cf45f1d",
  "gender": "Male",
  "age": 29,
  "height": "183 cm",
  "measurements": False,
  "agency": False,
  "tags": [
   "Studio",
   "Monochrome"
  ],
  "bio": "Berlin. Brandt's archive entries are short on purpose — he prefers the frames to carry the description.",
  "since": "2023"
 },
 {
  "slug": "noor-haddad",
  "name": "Noor Haddad",
  "stage": "",
  "featured": False,
  "avatar": "1500648767791-00dcc994a43e",
  "hero": "1500648767791-00dcc994a43e",
  "gender": "Female",
  "age": False,
  "height": False,
  "measurements": False,
  "agency": "Levant Artists",
  "tags": [
   "Portrait",
   "Reportage"
  ],
  "bio": "Amman. Haddad's work sits between portraiture and reportage; the archive keeps both.",
  "since": "2025"
 }
]

COLLECTIONS = [
 {
  "slug": "summer-editorial",
  "title": "Summer Editorial",
  "model": "yang-chenchen",
  "date": "2026.09.17",
  "tags": [
   "Fashion",
   "Editorial"
  ],
  "featured": True,
  "photos": [
   {
    "file": "demo/summer-editorial/1524253482453-3fed8d2fe12b.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/summer-editorial/1517365830460-955ce3ccd263.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/summer-editorial/1523413651479-597eb2da0ad6.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/summer-editorial/1521119989659-a83eee488004.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/summer-editorial/1525507119028-ed4c629a60a3.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/summer-editorial/1515886657613-9f3515b0c78f.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/summer-editorial/1508214751196-bcfd4ca60f91.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/summer-editorial/1524250502761-1ac6f2e30d43.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/summer-editorial/1507003211169-0a1dd7228f2d.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/summer-editorial/1475180098004-ca77a66827be.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/summer-editorial/1530785602389-07594beb8b73.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/summer-editorial/1500648767791-00dcc994a43e.jpg",
    "ar": "3/4"
   }
  ]
 },
 {
  "slug": "studio-monochrome",
  "title": "Studio Monochrome",
  "model": "yang-chenchen",
  "date": "2026.07.02",
  "tags": [
   "Studio",
   "Monochrome"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/studio-monochrome/1475180098004-ca77a66827be.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/studio-monochrome/1530785602389-07594beb8b73.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/studio-monochrome/1515886657613-9f3515b0c78f.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/studio-monochrome/1517841905240-472988babdf9.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/studio-monochrome/1502823403499-6ccfcf4fb453.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/studio-monochrome/1479064555552-3ef4979f8908.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/studio-monochrome/1521119989659-a83eee488004.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/studio-monochrome/1531427186611-ecfd6d936c79.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/studio-monochrome/1546525848-3ce03ca516f6.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/studio-monochrome/1512310604669-443f26c35f52.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/studio-monochrome/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/studio-monochrome/1506794778202-cad84cf45f1d.jpg",
    "ar": "3/2"
   }
  ]
 },
 {
  "slug": "harbour-light",
  "title": "Harbour Light",
  "model": "yang-chenchen",
  "date": "2026.05.21",
  "tags": [
   "Outdoor"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/harbour-light/1525507119028-ed4c629a60a3.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/harbour-light/1469334031218-e382a71b716b.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/harbour-light/1530785602389-07594beb8b73.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/harbour-light/1496747611176-843222e1e57c.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/harbour-light/1546525848-3ce03ca516f6.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/harbour-light/1487222477894-8943e31ef7b2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/harbour-light/1488161628813-04466f872be2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/harbour-light/1500648767791-00dcc994a43e.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/harbour-light/1541823709867-1b206113eafd.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/harbour-light/1534528741775-53994a69daeb.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/harbour-light/1485968579580-b6d095142e6e.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/harbour-light/1506794778202-cad84cf45f1d.jpg",
    "ar": "4/3"
   }
  ]
 },
 {
  "slug": "winter-wool",
  "title": "Winter Wool",
  "model": "yang-chenchen",
  "date": "2026.01.09",
  "tags": [
   "Fashion"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/winter-wool/1541823709867-1b206113eafd.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/winter-wool/1521119989659-a83eee488004.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/winter-wool/1525507119028-ed4c629a60a3.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/winter-wool/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/winter-wool/1485968579580-b6d095142e6e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/winter-wool/1469334031218-e382a71b716b.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/winter-wool/1519345182560-3f2917c472ef.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/winter-wool/1479064555552-3ef4979f8908.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/winter-wool/1554151228-14d9def656e4.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/winter-wool/1483985988355-763728e1935b.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/winter-wool/1488161628813-04466f872be2.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/winter-wool/1502823403499-6ccfcf4fb453.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/winter-wool/1515886657613-9f3515b0c78f.jpg",
    "ar": "3/4"
   }
  ]
 },
 {
  "slug": "glasshouse",
  "title": "Glasshouse",
  "model": "yang-chenchen",
  "date": "2025.11.14",
  "tags": [
   "Editorial"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/glasshouse/1492562080023-ab3db95bfbce.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/glasshouse/1507003211169-0a1dd7228f2d.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/glasshouse/1516726817505-f5ed825624d8.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/glasshouse/1494790108377-be9c29b29330.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/glasshouse/1519085360753-af0119f7cbe7.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/glasshouse/1483985988355-763728e1935b.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/glasshouse/1488161628813-04466f872be2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/glasshouse/1519345182560-3f2917c472ef.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/glasshouse/1479064555552-3ef4979f8908.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/glasshouse/1524253482453-3fed8d2fe12b.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/glasshouse/1438761681033-6461ffad8d80.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/glasshouse/1502823403499-6ccfcf4fb453.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/glasshouse/1529626455594-4ff0802cfb7e.jpg",
    "ar": "2/3"
   }
  ]
 },
 {
  "slug": "concrete-garden",
  "title": "Concrete Garden",
  "model": "yang-chenchen",
  "date": "2025.08.30",
  "tags": [
   "Outdoor",
   "Editorial"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/concrete-garden/1506794778202-cad84cf45f1d.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/concrete-garden/1531746020798-e6953c6e8e04.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/concrete-garden/1496747611176-843222e1e57c.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/concrete-garden/1541823709867-1b206113eafd.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/concrete-garden/1554151228-14d9def656e4.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/concrete-garden/1508214751196-bcfd4ca60f91.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/concrete-garden/1504703395950-b89145a5425b.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/concrete-garden/1438761681033-6461ffad8d80.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/concrete-garden/1529626455594-4ff0802cfb7e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/concrete-garden/1531427186611-ecfd6d936c79.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/concrete-garden/1546525848-3ce03ca516f6.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/concrete-garden/1524504388940-b1c1722653e1.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/concrete-garden/1475180098004-ca77a66827be.jpg",
    "ar": "2/3"
   }
  ]
 },
 {
  "slug": "nocturne",
  "title": "Nocturne",
  "model": "imogen-vale",
  "date": "2026.08.28",
  "tags": [
   "Studio",
   "Monochrome"
  ],
  "featured": True,
  "photos": [
   {
    "file": "demo/nocturne/1438761681033-6461ffad8d80.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/nocturne/1534528741775-53994a69daeb.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/nocturne/1554151228-14d9def656e4.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/nocturne/1531746020798-e6953c6e8e04.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/nocturne/1531123897727-8f129e1688ce.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/nocturne/1544005313-94ddf0286df2.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/nocturne/1507003211169-0a1dd7228f2d.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/nocturne/1483985988355-763728e1935b.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/nocturne/1524250502761-1ac6f2e30d43.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/nocturne/1506794778202-cad84cf45f1d.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/nocturne/1524253482453-3fed8d2fe12b.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/nocturne/1524504388940-b1c1722653e1.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/nocturne/1517841905240-472988babdf9.jpg",
    "ar": "3/4"
   }
  ]
 },
 {
  "slug": "linen-days",
  "title": "Linen Days",
  "model": "imogen-vale",
  "date": "2026.06.11",
  "tags": [
   "Fashion",
   "Outdoor"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/linen-days/1530785602389-07594beb8b73.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/linen-days/1479064555552-3ef4979f8908.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/linen-days/1469334031218-e382a71b716b.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/linen-days/1524638431109-93d95c968f03.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/linen-days/1544005313-94ddf0286df2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/linen-days/1492562080023-ab3db95bfbce.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/linen-days/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/linen-days/1519699047748-de8e457a634e.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/linen-days/1502823403499-6ccfcf4fb453.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/linen-days/1487222477894-8943e31ef7b2.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/linen-days/1496747611176-843222e1e57c.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/linen-days/1524504388940-b1c1722653e1.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/linen-days/1524250502761-1ac6f2e30d43.jpg",
    "ar": "16/9"
   }
  ]
 },
 {
  "slug": "salt-and-silver",
  "title": "Salt & Silver",
  "model": "imogen-vale",
  "date": "2026.03.04",
  "tags": [
   "Outdoor",
   "Monochrome"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/salt-and-silver/1531427186611-ecfd6d936c79.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/salt-and-silver/1554151228-14d9def656e4.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/salt-and-silver/1541101767792-f9b2b1c4f127.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/salt-and-silver/1488161628813-04466f872be2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/salt-and-silver/1523413651479-597eb2da0ad6.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/salt-and-silver/1507003211169-0a1dd7228f2d.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/salt-and-silver/1519085360753-af0119f7cbe7.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/salt-and-silver/1524638431109-93d95c968f03.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/salt-and-silver/1503342217505-b0a15ec3261c.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/salt-and-silver/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/salt-and-silver/1502823403499-6ccfcf4fb453.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/salt-and-silver/1517841905240-472988babdf9.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/salt-and-silver/1524504388940-b1c1722653e1.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/salt-and-silver/1500648767791-00dcc994a43e.jpg",
    "ar": "2/3"
   }
  ]
 },
 {
  "slug": "terrazzo",
  "title": "Terrazzo",
  "model": "imogen-vale",
  "date": "2025.10.19",
  "tags": [
   "Studio"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/terrazzo/1521119989659-a83eee488004.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/terrazzo/1544005313-94ddf0286df2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/terrazzo/1541823709867-1b206113eafd.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/terrazzo/1524250502761-1ac6f2e30d43.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/terrazzo/1521572163474-6864f9cf17ab.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/terrazzo/1500648767791-00dcc994a43e.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/terrazzo/1503342217505-b0a15ec3261c.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/terrazzo/1492562080023-ab3db95bfbce.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/terrazzo/1488161628813-04466f872be2.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/terrazzo/1530785602389-07594beb8b73.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/terrazzo/1516726817505-f5ed825624d8.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/terrazzo/1517841905240-472988babdf9.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/terrazzo/1524253482453-3fed8d2fe12b.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/terrazzo/1504703395950-b89145a5425b.jpg",
    "ar": "1/1"
   }
  ]
 },
 {
  "slug": "first-light",
  "title": "First Light",
  "model": "sora-nakamura",
  "date": "2026.09.02",
  "tags": [
   "Available Light",
   "Portrait"
  ],
  "featured": True,
  "photos": [
   {
    "file": "demo/first-light/1521572163474-6864f9cf17ab.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/first-light/1503342217505-b0a15ec3261c.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/first-light/1546525848-3ce03ca516f6.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/first-light/1531427186611-ecfd6d936c79.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/first-light/1469334031218-e382a71b716b.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/first-light/1502823403499-6ccfcf4fb453.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/first-light/1500648767791-00dcc994a43e.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/first-light/1475180098004-ca77a66827be.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/first-light/1512310604669-443f26c35f52.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/first-light/1507003211169-0a1dd7228f2d.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/first-light/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/first-light/1534528741775-53994a69daeb.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/first-light/1506794778202-cad84cf45f1d.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/first-light/1508214751196-bcfd4ca60f91.jpg",
    "ar": "1/1"
   }
  ]
 },
 {
  "slug": "paper-lanterns",
  "title": "Paper Lanterns",
  "model": "sora-nakamura",
  "date": "2026.04.16",
  "tags": [
   "Available Light"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/paper-lanterns/1531123897727-8f129e1688ce.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/paper-lanterns/1524504388940-b1c1722653e1.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/paper-lanterns/1508214751196-bcfd4ca60f91.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/paper-lanterns/1500648767791-00dcc994a43e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/paper-lanterns/1534528741775-53994a69daeb.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/paper-lanterns/1502823403499-6ccfcf4fb453.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/paper-lanterns/1521572163474-6864f9cf17ab.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/paper-lanterns/1512310604669-443f26c35f52.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/paper-lanterns/1469334031218-e382a71b716b.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/paper-lanterns/1485968579580-b6d095142e6e.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/paper-lanterns/1479064555552-3ef4979f8908.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/paper-lanterns/1517841905240-472988babdf9.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/paper-lanterns/1519699047748-de8e457a634e.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/paper-lanterns/1531427186611-ecfd6d936c79.jpg",
    "ar": "3/2"
   }
  ]
 },
 {
  "slug": "quiet-hours",
  "title": "Quiet Hours",
  "model": "sora-nakamura",
  "date": "2025.12.07",
  "tags": [
   "Portrait"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/quiet-hours/1485968579580-b6d095142e6e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1475180098004-ca77a66827be.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/quiet-hours/1521119989659-a83eee488004.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/quiet-hours/1515886657613-9f3515b0c78f.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/quiet-hours/1519345182560-3f2917c472ef.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/quiet-hours/1534528741775-53994a69daeb.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1506794778202-cad84cf45f1d.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1502823403499-6ccfcf4fb453.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1516726817505-f5ed825624d8.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1546525848-3ce03ca516f6.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1507003211169-0a1dd7228f2d.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1438761681033-6461ffad8d80.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/quiet-hours/1500648767791-00dcc994a43e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/quiet-hours/1479064555552-3ef4979f8908.jpg",
    "ar": "3/2"
   }
  ]
 },
 {
  "slug": "neue-sachlichkeit",
  "title": "Neue Sachlichkeit",
  "model": "mara-lindqvist",
  "date": "2026.08.05",
  "tags": [
   "Editorial",
   "Monochrome"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/neue-sachlichkeit/1496747611176-843222e1e57c.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/neue-sachlichkeit/1524638431109-93d95c968f03.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/neue-sachlichkeit/1488161628813-04466f872be2.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/neue-sachlichkeit/1521119989659-a83eee488004.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/neue-sachlichkeit/1525507119028-ed4c629a60a3.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/neue-sachlichkeit/1438761681033-6461ffad8d80.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/neue-sachlichkeit/1519699047748-de8e457a634e.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/neue-sachlichkeit/1487222477894-8943e31ef7b2.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/neue-sachlichkeit/1515886657613-9f3515b0c78f.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/neue-sachlichkeit/1534528741775-53994a69daeb.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/neue-sachlichkeit/1529626455594-4ff0802cfb7e.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/neue-sachlichkeit/1517841905240-472988babdf9.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/neue-sachlichkeit/1503342217505-b0a15ec3261c.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/neue-sachlichkeit/1494790108377-be9c29b29330.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/neue-sachlichkeit/1504703395950-b89145a5425b.jpg",
    "ar": "3/4"
   }
  ]
 },
 {
  "slug": "baltic",
  "title": "Baltic",
  "model": "mara-lindqvist",
  "date": "2026.02.23",
  "tags": [
   "Outdoor"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/baltic/1508214751196-bcfd4ca60f91.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/baltic/1483985988355-763728e1935b.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/baltic/1504703395950-b89145a5425b.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/baltic/1524504388940-b1c1722653e1.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/baltic/1502823403499-6ccfcf4fb453.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/baltic/1529626455594-4ff0802cfb7e.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/baltic/1506794778202-cad84cf45f1d.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/baltic/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/baltic/1438761681033-6461ffad8d80.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/baltic/1541823709867-1b206113eafd.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/baltic/1521119989659-a83eee488004.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/baltic/1494790108377-be9c29b29330.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/baltic/1507003211169-0a1dd7228f2d.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/baltic/1531123897727-8f129e1688ce.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/baltic/1519345182560-3f2917c472ef.jpg",
    "ar": "16/9"
   }
  ]
 },
 {
  "slug": "field-notes",
  "title": "Field Notes",
  "model": "mara-lindqvist",
  "date": "2025.09.12",
  "tags": [
   "Editorial"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/field-notes/1507003211169-0a1dd7228f2d.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/field-notes/1519345182560-3f2917c472ef.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/field-notes/1492562080023-ab3db95bfbce.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/field-notes/1487222477894-8943e31ef7b2.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/field-notes/1512310604669-443f26c35f52.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/field-notes/1530785602389-07594beb8b73.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/field-notes/1531746020798-e6953c6e8e04.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/field-notes/1529626455594-4ff0802cfb7e.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/field-notes/1524253482453-3fed8d2fe12b.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/field-notes/1531123897727-8f129e1688ce.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/field-notes/1517365830460-955ce3ccd263.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/field-notes/1494790108377-be9c29b29330.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/field-notes/1504703395950-b89145a5425b.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/field-notes/1500648767791-00dcc994a43e.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/field-notes/1546525848-3ce03ca516f6.jpg",
    "ar": "4/5"
   }
  ]
 },
 {
  "slug": "monsoon",
  "title": "Monsoon",
  "model": "priya-raghavan",
  "date": "2026.07.24",
  "tags": [
   "Outdoor",
   "Colour"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/monsoon/1524504388940-b1c1722653e1.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/monsoon/1500648767791-00dcc994a43e.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/monsoon/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/monsoon/1504703395950-b89145a5425b.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/monsoon/1475180098004-ca77a66827be.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/monsoon/1524638431109-93d95c968f03.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/monsoon/1502823403499-6ccfcf4fb453.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/monsoon/1508214751196-bcfd4ca60f91.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/monsoon/1506794778202-cad84cf45f1d.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/monsoon/1541101767792-f9b2b1c4f127.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/monsoon/1541823709867-1b206113eafd.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/monsoon/1529626455594-4ff0802cfb7e.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/monsoon/1488161628813-04466f872be2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/monsoon/1519345182560-3f2917c472ef.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/monsoon/1512310604669-443f26c35f52.jpg",
    "ar": "3/2"
   }
  ]
 },
 {
  "slug": "vermilion",
  "title": "Vermilion",
  "model": "priya-raghavan",
  "date": "2026.01.30",
  "tags": [
   "Colour",
   "Fashion"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/vermilion/1494790108377-be9c29b29330.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/vermilion/1531123897727-8f129e1688ce.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/vermilion/1519085360753-af0119f7cbe7.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/vermilion/1438761681033-6461ffad8d80.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/vermilion/1507003211169-0a1dd7228f2d.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/vermilion/1554151228-14d9def656e4.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/vermilion/1524253482453-3fed8d2fe12b.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/vermilion/1531746020798-e6953c6e8e04.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/vermilion/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/vermilion/1502823403499-6ccfcf4fb453.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/vermilion/1517841905240-472988babdf9.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/vermilion/1529626455594-4ff0802cfb7e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/vermilion/1521119989659-a83eee488004.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/vermilion/1508214751196-bcfd4ca60f91.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/vermilion/1531427186611-ecfd6d936c79.jpg",
    "ar": "5/4"
   }
  ]
 },
 {
  "slug": "altiplano",
  "title": "Altiplano",
  "model": "camille-okonjo",
  "date": "2026.06.27",
  "tags": [
   "Outdoor",
   "Colour"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/altiplano/1524638431109-93d95c968f03.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/altiplano/1529626455594-4ff0802cfb7e.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/altiplano/1521572163474-6864f9cf17ab.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/altiplano/1541823709867-1b206113eafd.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/altiplano/1516726817505-f5ed825624d8.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/altiplano/1531427186611-ecfd6d936c79.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/altiplano/1517841905240-472988babdf9.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/altiplano/1554151228-14d9def656e4.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/altiplano/1544005313-94ddf0286df2.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/altiplano/1496747611176-843222e1e57c.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/altiplano/1530785602389-07594beb8b73.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/altiplano/1494790108377-be9c29b29330.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/altiplano/1508214751196-bcfd4ca60f91.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/altiplano/1523413651479-597eb2da0ad6.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/altiplano/1438761681033-6461ffad8d80.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/altiplano/1519085360753-af0119f7cbe7.jpg",
    "ar": "2/3"
   }
  ]
 },
 {
  "slug": "dune",
  "title": "Dune",
  "model": "camille-okonjo",
  "date": "2026.03.19",
  "tags": [
   "Outdoor"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/dune/1541101767792-f9b2b1c4f127.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1487222477894-8943e31ef7b2.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/dune/1506794778202-cad84cf45f1d.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1531746020798-e6953c6e8e04.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1524253482453-3fed8d2fe12b.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/dune/1512310604669-443f26c35f52.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/dune/1531123897727-8f129e1688ce.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1519085360753-af0119f7cbe7.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1531427186611-ecfd6d936c79.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/dune/1519699047748-de8e457a634e.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/dune/1521572163474-6864f9cf17ab.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1523413651479-597eb2da0ad6.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1554151228-14d9def656e4.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1479064555552-3ef4979f8908.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/dune/1516726817505-f5ed825624d8.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/dune/1503342217505-b0a15ec3261c.jpg",
    "ar": "2/3"
   }
  ]
 },
 {
  "slug": "cold-storage",
  "title": "Cold Storage",
  "model": "elias-brandt",
  "date": "2026.05.08",
  "tags": [
   "Studio",
   "Monochrome"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/cold-storage/1504703395950-b89145a5425b.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/cold-storage/1512310604669-443f26c35f52.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/cold-storage/1531746020798-e6953c6e8e04.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/cold-storage/1530785602389-07594beb8b73.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/cold-storage/1508214751196-bcfd4ca60f91.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/cold-storage/1521119989659-a83eee488004.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/cold-storage/1534528741775-53994a69daeb.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/cold-storage/1515886657613-9f3515b0c78f.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/cold-storage/1496747611176-843222e1e57c.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/cold-storage/1524638431109-93d95c968f03.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/cold-storage/1487222477894-8943e31ef7b2.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/cold-storage/1523413651479-597eb2da0ad6.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/cold-storage/1483985988355-763728e1935b.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/cold-storage/1494790108377-be9c29b29330.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/cold-storage/1529626455594-4ff0802cfb7e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/cold-storage/1438761681033-6461ffad8d80.jpg",
    "ar": "3/2"
   }
  ]
 },
 {
  "slug": "arcade",
  "title": "Arcade",
  "model": "elias-brandt",
  "date": "2025.11.26",
  "tags": [
   "Studio"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/arcade/1519699047748-de8e457a634e.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/arcade/1492562080023-ab3db95bfbce.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/arcade/1502823403499-6ccfcf4fb453.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/arcade/1488161628813-04466f872be2.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/arcade/1529626455594-4ff0802cfb7e.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/arcade/1519345182560-3f2917c472ef.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/arcade/1517365830460-955ce3ccd263.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/arcade/1521119989659-a83eee488004.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/arcade/1530785602389-07594beb8b73.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/arcade/1519085360753-af0119f7cbe7.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/arcade/1507003211169-0a1dd7228f2d.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/arcade/1523413651479-597eb2da0ad6.jpg",
    "ar": "3/2"
   },
   {
    "file": "demo/arcade/1531427186611-ecfd6d936c79.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/arcade/1531123897727-8f129e1688ce.jpg",
    "ar": "16/9"
   },
   {
    "file": "demo/arcade/1494790108377-be9c29b29330.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/arcade/1487222477894-8943e31ef7b2.jpg",
    "ar": "2/3"
   }
  ]
 },
 {
  "slug": "still-water",
  "title": "Still Water",
  "model": "noor-haddad",
  "date": "2026.08.14",
  "tags": [
   "Portrait",
   "Reportage"
  ],
  "featured": False,
  "photos": [
   {
    "file": "demo/still-water/1524250502761-1ac6f2e30d43.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/still-water/1519699047748-de8e457a634e.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/still-water/1524253482453-3fed8d2fe12b.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/still-water/1531123897727-8f129e1688ce.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/still-water/1503342217505-b0a15ec3261c.jpg",
    "ar": "4/3"
   },
   {
    "file": "demo/still-water/1492707892479-7bc8d5a4ee93.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/still-water/1438761681033-6461ffad8d80.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/still-water/1517841905240-472988babdf9.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/still-water/1475180098004-ca77a66827be.jpg",
    "ar": "5/4"
   },
   {
    "file": "demo/still-water/1515886657613-9f3515b0c78f.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/still-water/1530785602389-07594beb8b73.jpg",
    "ar": "1/1"
   },
   {
    "file": "demo/still-water/1523413651479-597eb2da0ad6.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/still-water/1496747611176-843222e1e57c.jpg",
    "ar": "4/5"
   },
   {
    "file": "demo/still-water/1506794778202-cad84cf45f1d.jpg",
    "ar": "2/3"
   },
   {
    "file": "demo/still-water/1494790108377-be9c29b29330.jpg",
    "ar": "3/4"
   },
   {
    "file": "demo/still-water/1546525848-3ce03ca516f6.jpg",
    "ar": "1/1"
   }
  ]
 }
]
