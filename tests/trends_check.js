// Prints the numbers the Trends and Today pages compute from a history CSV (shared calc.js).
const fs = require("fs");
const Calc = require("../calc.js");
const rows = Calc.parseCSV(fs.readFileSync(process.argv[2], "utf8"));
const latest = Calc.latestDate(rows);
const strip = o => JSON.parse(JSON.stringify(o));
console.log(JSON.stringify({
  latest,
  moves: Calc.moves(rows, latest),
  subscribers_since_first: Calc.sinceFirst(rows, "subscribers"),
  videos_since_first: Calc.sinceFirst(rows, "videos"),
  views_gains: Calc.biggestGains(rows, "views"),
  spread_subscribers: strip(Calc.spread(rows, "subscribers")),
  median_views_per_video: Calc.median(Calc.onDate(rows, latest).filter(r => r.views_per_video != null).map(r => r.views_per_video)),
}));
