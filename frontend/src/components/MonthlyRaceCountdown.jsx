import { useEffect, useState } from "react";

const COUNTDOWN_UNITS = [
  { key: "days", label: "Days" },
  { key: "hours", label: "Hours" },
  { key: "minutes", label: "Min" },
  { key: "seconds", label: "Sec" },
];
const RACE_START_DAY = 19;

function getRaceWindow(now = new Date()) {
  let start = new Date(Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    RACE_START_DAY,
  ));
  const firstEnd = new Date(start);
  firstEnd.setUTCMonth(firstEnd.getUTCMonth() + 1);
  if (now >= firstEnd) start = firstEnd;

  const end = new Date(start);
  end.setUTCMonth(end.getUTCMonth() + 1);
  return { start, end };
}

function getCountdown(now = new Date()) {
  const { start, end } = getRaceWindow(now);
  const remaining = Math.max(0, end.getTime() - now.getTime());
  const totalSeconds = Math.floor(remaining / 1000);

  return {
    start,
    end,
    values: {
      days: Math.floor(totalSeconds / 86400),
      hours: Math.floor((totalSeconds % 86400) / 3600),
      minutes: Math.floor((totalSeconds % 3600) / 60),
      seconds: totalSeconds % 60,
    },
  };
}

const formatUtcDate = (date) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);

export default function MonthlyRaceCountdown() {
  const [countdown, setCountdown] = useState(() => getCountdown());

  useEffect(() => {
    const update = () => setCountdown(getCountdown());
    const timer = window.setInterval(update, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const isPreRace = new Date() < countdown.start;
  const label = isPreRace ? "NEXT RACE" : "WAGER RACE";
  const accessibleTime = COUNTDOWN_UNITS
    .map(({ key, label: unitLabel }) => `${countdown.values[key]} ${unitLabel.toLowerCase()}`)
    .join(", ");

  return (
    <section className="leaderboard-race-panel" aria-labelledby="monthly-race-title">
      <div className="leaderboard-race-kicker">{label}</div>
      <h2 id="monthly-race-title" className="leaderboard-race-title">
        <span>$500</span> Leaderboard
      </h2>
      <p className="leaderboard-race-copy">
        Ranked by how much you&apos;ve wagered — top of the board takes the prize.
      </p>

      <div
        className="leaderboard-race-countdown"
        role="timer"
        aria-label={`Monthly wager race countdown: ${accessibleTime}`}
      >
        {COUNTDOWN_UNITS.map(({ key, label: unitLabel }) => (
          <div className="leaderboard-race-unit" key={key}>
            <span className="countdown-value" key={`${key}-${countdown.values[key]}`}>
              {String(countdown.values[key]).padStart(2, "0")}
            </span>
            <span className="countdown-unit-label">{unitLabel}</span>
          </div>
        ))}
      </div>

      <div className="leaderboard-race-window">
        {isPreRace ? "Window opens" : "Window ends"} {formatUtcDate(isPreRace ? countdown.start : countdown.end)} · 00:00 UTC
      </div>
    </section>
  );
}
