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
  views_since_first: Calc.sinceFirst(rows, "views"),
  videos_since_first: Calc.sinceFirst(rows, "videos"),
  views_gains: Calc.biggestGains(rows, "views"),
  spread_subscribers: strip(Calc.spread(rows, "subscribers")),
  totals_subscribers: Calc.totalsByDate(rows, "subscribers"),
  totals_views: Calc.totalsByDate(rows, "views"),
  total_change_subscribers: Calc.totalChange(rows, "subscribers"),
  total_change_views: Calc.totalChange(rows, "views"),
  leaders_views: Calc.leaders(rows, "views", 17),
  leaders_subscribers: Calc.leaders(rows, "subscribers", 17),
  leaders_likes_recent: Calc.leaders(rows, "likes_recent", 17),
  leaders_comments_recent: Calc.leaders(rows, "comments_recent", 17),
  median_views_per_video: Calc.median(Calc.onDate(rows, latest).filter(r => r.views_per_video != null).map(r => r.views_per_video)),
}));
