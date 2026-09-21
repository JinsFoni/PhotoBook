/* ==========================================================================
   Photo Collection — mock archive data
   Deterministic: the same collection always renders the same frames,
   so the design can be reviewed against a stable set of images.
   ========================================================================== */

window.ARCHIVE = (function () {
  var BASE = "https://images.unsplash.com/photo-";

  /* ---- image URL builder -------------------------------------------------
     Unsplash crops server-side, so every frame is delivered at the exact
     aspect ratio it is displayed at. No client-side letterboxing.          */
  function src(id, o) {
    o = o || {};
    var w = Math.round(o.w || 900);
    var ar = o.ar || null;
    var p = ["w=" + w, "q=" + (o.q || 72), "auto=format", "fit=crop"];
    if (ar) {
      p.push("h=" + Math.round(w / ar));
      p.push("crop=" + (o.crop || "entropy"));
    } else if (o.h) {
      p.push("h=" + Math.round(o.h));
      p.push("crop=" + (o.crop || "entropy"));
    }
    return BASE + id + "?" + p.join("&");
  }

  function ratio(str) {
    var a = str.split("/");
    return Number(a[0]) / Number(a[1]);
  }

  function rng(seed) {
    var s = (seed * 2654435761) >>> 0 || 1;
    return function () {
      s = (s * 1664525 + 1013904223) >>> 0;
      return s / 4294967296;
    };
  }

  /* ---- image pool ------------------------------------------------------- */
  var POOL = [
    "1529626455594-4ff0802cfb7e", "1494790108377-be9c29b29330",
    "1438761681033-6461ffad8d80", "1534528741775-53994a69daeb",
    "1517841905240-472988babdf9", "1524504388940-b1c1722653e1",
    "1502823403499-6ccfcf4fb453", "1506794778202-cad84cf45f1d",
    "1500648767791-00dcc994a43e", "1519085360753-af0119f7cbe7",
    "1507003211169-0a1dd7228f2d", "1492562080023-ab3db95bfbce",
    "1488161628813-04466f872be2", "1544005313-94ddf0286df2",
    "1508214751196-bcfd4ca60f91", "1541823709867-1b206113eafd",
    "1483985988355-763728e1935b", "1469334031218-e382a71b716b",
    "1496747611176-843222e1e57c", "1487222477894-8943e31ef7b2",
    "1525507119028-ed4c629a60a3", "1479064555552-3ef4979f8908",
    "1515886657613-9f3515b0c78f", "1485968579580-b6d095142e6e",
    "1475180098004-ca77a66827be", "1517365830460-955ce3ccd263",
    "1524250502761-1ac6f2e30d43", "1531123897727-8f129e1688ce",
    "1524253482453-3fed8d2fe12b", "1531746020798-e6953c6e8e04",
    "1519699047748-de8e457a634e", "1521572163474-6864f9cf17ab",
    "1503342217505-b0a15ec3261c", "1492707892479-7bc8d5a4ee93",
    "1504703395950-b89145a5425b", "1519345182560-3f2917c472ef",
    "1521119989659-a83eee488004", "1546525848-3ce03ca516f6",
    "1512310604669-443f26c35f52", "1541101767792-f9b2b1c4f127",
    "1531427186611-ecfd6d936c79", "1554151228-14d9def656e4",
    "1516726817505-f5ed825624d8", "1524638431109-93d95c968f03",
    "1530785602389-07594beb8b73", "1523413651479-597eb2da0ad6"
  ];

  /* Portrait ratios weighted toward tall frames, as a real archive would be. */
  var RATIOS = ["2/3", "3/4", "4/5", "2/3", "1/1", "3/2", "2/3", "5/4", "4/3", "3/4", "2/3", "16/9"];

  /* ---- models ----------------------------------------------------------- */
  var MODELS = [
    {
      slug: "yang-chenchen", name: "Yang Chenchen", stage: "", featured: true,
      avatar: "1529626455594-4ff0802cfb7e", hero: "1529626455594-4ff0802cfb7e",
      gender: "Female", age: null, height: "168 cm", measurements: null,
      agency: "ABC Agency", tags: ["Fashion", "Portrait", "Editorial"],
      bio: "Shot between Shanghai and Lisbon, Chenchen's archive work moves between sharp tailoring and unstructured linen. She reads a room quickly and gives the camera very little, which is the point.",
      since: "2024"
    },
    {
      slug: "imogen-vale", name: "Imogen Vale", stage: "VALE", featured: true,
      avatar: "1494790108377-be9c29b29330", hero: "1494790108377-be9c29b29330",
      gender: "Female", age: 27, height: "174 cm", measurements: "81-61-88",
      agency: "Vale Management", tags: ["Fashion", "Movement", "Studio"],
      bio: "London-based, trained in dance. Vale's frames are usually caught mid-movement, so the archive holds more outtakes than selects.",
      since: "2023"
    },
    {
      slug: "sora-nakamura", name: "Sora Nakamura", stage: "", featured: true,
      avatar: "1534528741775-53994a69daeb", hero: "1534528741775-53994a69daeb",
      gender: "Female", age: null, height: null, measurements: null,
      agency: null, tags: ["Available Light", "Portrait"],
      bio: "Nakamura works almost exclusively in available light. The result is a body of work with an unusually narrow palette and an unusually wide range of expression.",
      since: "2025"
    },
    {
      slug: "mara-lindqvist", name: "Mara Lindqvist", stage: "", featured: true,
      avatar: "1517841905240-472988babdf9", hero: "1517841905240-472988babdf9",
      gender: "Female", age: 31, height: "179 cm", measurements: null,
      agency: "Nordisk", tags: ["Editorial", "Studio", "Monochrome"],
      bio: "Stockholm. Lindqvist came to the archive from architecture photography, and it shows in the way she holds a line.",
      since: "2022"
    },
    {
      slug: "priya-raghavan", name: "Priya Raghavan", stage: "", featured: false,
      avatar: "1524504388940-b1c1722653e1", hero: "1524504388940-b1c1722653e1",
      gender: "Female", age: 24, height: "165 cm", measurements: "84-63-89",
      agency: null, tags: ["Outdoor", "Fashion"],
      bio: "Mumbai. Raghavan's sittings run long and get quieter as they go; most of this archive is from the last hour.",
      since: "2025"
    },
    {
      slug: "camille-okonjo", name: "Camille Okonjo", stage: "", featured: false,
      avatar: "1502823403499-6ccfcf4fb453", hero: "1502823403499-6ccfcf4fb453",
      gender: "Female", age: null, height: "171 cm", measurements: null,
      agency: "Atelier 9", tags: ["Outdoor", "Colour", "Editorial"],
      bio: "Lagos and Marseille. Okonjo shoots in colour almost exclusively, and almost always outdoors.",
      since: "2024"
    },
    {
      slug: "elias-brandt", name: "Elias Brandt", stage: "", featured: false,
      avatar: "1506794778202-cad84cf45f1d", hero: "1506794778202-cad84cf45f1d",
      gender: "Male", age: 29, height: "183 cm", measurements: null,
      agency: null, tags: ["Studio", "Monochrome"],
      bio: "Berlin. Brandt's archive entries are short on purpose — he prefers the frames to carry the description.",
      since: "2023"
    },
    {
      slug: "noor-haddad", name: "Noor Haddad", stage: "", featured: false,
      avatar: "1500648767791-00dcc994a43e", hero: "1500648767791-00dcc994a43e",
      gender: "Female", age: null, height: null, measurements: null,
      agency: "Levant Artists", tags: ["Portrait", "Reportage"],
      bio: "Amman. Haddad's work sits between portraiture and reportage; the archive keeps both.",
      since: "2025"
    }
  ];

  /* ---- collections ------------------------------------------------------ */
  var RAW = [
    ["summer-editorial", "Summer Editorial", "yang-chenchen", "2026.09.17", ["Fashion", "Editorial"], true, 0],
    ["studio-monochrome", "Studio Monochrome", "yang-chenchen", "2026.07.02", ["Studio", "Monochrome"], false, 1],
    ["harbour-light", "Harbour Light", "yang-chenchen", "2026.05.21", ["Outdoor"], false, 2],
    ["winter-wool", "Winter Wool", "yang-chenchen", "2026.01.09", ["Fashion"], false, 3],
    ["glasshouse", "Glasshouse", "yang-chenchen", "2025.11.14", ["Editorial"], false, 4],
    ["concrete-garden", "Concrete Garden", "yang-chenchen", "2025.08.30", ["Outdoor", "Editorial"], false, 5],
    ["nocturne", "Nocturne", "imogen-vale", "2026.08.28", ["Studio", "Monochrome"], true, 6],
    ["linen-days", "Linen Days", "imogen-vale", "2026.06.11", ["Fashion", "Outdoor"], false, 7],
    ["salt-and-silver", "Salt & Silver", "imogen-vale", "2026.03.04", ["Outdoor", "Monochrome"], false, 8],
    ["terrazzo", "Terrazzo", "imogen-vale", "2025.10.19", ["Studio"], false, 9],
    ["first-light", "First Light", "sora-nakamura", "2026.09.02", ["Available Light", "Portrait"], true, 10],
    ["paper-lanterns", "Paper Lanterns", "sora-nakamura", "2026.04.16", ["Available Light"], false, 11],
    ["quiet-hours", "Quiet Hours", "sora-nakamura", "2025.12.07", ["Portrait"], false, 12],
    ["neue-sachlichkeit", "Neue Sachlichkeit", "mara-lindqvist", "2026.08.05", ["Editorial", "Monochrome"], false, 13],
    ["baltic", "Baltic", "mara-lindqvist", "2026.02.23", ["Outdoor"], false, 14],
    ["field-notes", "Field Notes", "mara-lindqvist", "2025.09.12", ["Editorial"], false, 15],
    ["monsoon", "Monsoon", "priya-raghavan", "2026.07.24", ["Outdoor", "Colour"], false, 16],
    ["vermilion", "Vermilion", "priya-raghavan", "2026.01.30", ["Colour", "Fashion"], false, 17],
    ["altiplano", "Altiplano", "camille-okonjo", "2026.06.27", ["Outdoor", "Colour"], false, 18],
    ["dune", "Dune", "camille-okonjo", "2026.03.19", ["Outdoor"], false, 19],
    ["cold-storage", "Cold Storage", "elias-brandt", "2026.05.08", ["Studio", "Monochrome"], false, 20],
    ["arcade", "Arcade", "elias-brandt", "2025.11.26", ["Studio"], false, 21],
    ["still-water", "Still Water", "noor-haddad", "2026.08.14", ["Portrait", "Reportage"], false, 22]
  ];

  var COLLECTIONS = RAW.map(function (r) {
    var slug = r[0], title = r[1], model = r[2], date = r[3], tags = r[4],
      featured = r[5], seed = r[6];
    var rand = rng(seed + 7);
    var n = 9 + Math.floor(rand() * 9); // 9–17 frames
    var photos = [];
    var used = {};
    for (var i = 0; i < n; i++) {
      var idx = Math.floor(rand() * POOL.length);
      var guard = 0;
      while (used[idx] && guard++ < 40) idx = (idx + 1) % POOL.length;
      used[idx] = true;
      photos.push({ id: POOL[idx], ar: RATIOS[Math.floor(rand() * RATIOS.length)] });
    }
    return {
      slug: slug,
      title: title,
      model: model,
      date: date,
      tags: tags,
      featured: featured,
      status: "published",
      cover: photos[0],
      photos: photos
    };
  });

  var bySlug = {};
  COLLECTIONS.forEach(function (c) { bySlug[c.slug] = c; });
  var modelBySlug = {};
  MODELS.forEach(function (m) { modelBySlug[m.slug] = m; });

  /* ---- derived ---------------------------------------------------------- */
  MODELS.forEach(function (m) {
    m.works = COLLECTIONS.filter(function (c) { return c.model === m.slug; });
    m.count = m.works.length;
    m.photoCount = m.works.reduce(function (a, c) { return a + c.photos.length; }, 0);
    m.latest = m.works[0] ? m.works[0].date : null;
  });

  var TAG_COUNTS = {};
  COLLECTIONS.forEach(function (c) {
    c.tags.forEach(function (t) {
      TAG_COUNTS[t] = TAG_COUNTS[t] || { name: t, collections: 0, models: {} };
      TAG_COUNTS[t].collections++;
      TAG_COUNTS[t].models[c.model] = true;
    });
  });
  var TAGS = Object.keys(TAG_COUNTS).map(function (k) {
    return { name: k, collections: TAG_COUNTS[k].collections, models: Object.keys(TAG_COUNTS[k].models).length };
  }).sort(function (a, b) { return b.collections - a.collections; });

  var AGENCIES = MODELS.map(function (m) { return m.agency; })
    .filter(Boolean)
    .filter(function (v, i, a) { return a.indexOf(v) === i; })
    .sort();

  var FEATURED = COLLECTIONS.filter(function (c) { return c.featured; });

  /* ---- current user ----------------------------------------------------- */
  var USER = {
    name: "Lin Wei",
    email: "lin.wei@example.com",
    role: "user",
    since: "March 2025",
    avatar: "1519085360753-af0119f7cbe7"
  };

  return {
    src: src,
    ratio: ratio,
    POOL: POOL,
    MODELS: MODELS,
    COLLECTIONS: COLLECTIONS,
    TAGS: TAGS,
    AGENCIES: AGENCIES,
    FEATURED: FEATURED,
    USER: USER,
    model: function (slug) { return modelBySlug[slug]; },
    collection: function (slug) { return bySlug[slug]; },
    /* every photo in the archive, flattened */
    allPhotos: function () {
      var out = [];
      COLLECTIONS.forEach(function (c) {
        c.photos.forEach(function (p, i) {
          out.push({ id: p.id, ar: p.ar, collection: c.slug, index: i });
        });
      });
      return out;
    }
  };
})();
