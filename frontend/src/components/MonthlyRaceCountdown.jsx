import { useEffect, useState } from "react";

const COUNTDOWN_UNITS = [
  { key: "days", label: "Days" },
  { key: "hours", label: "Hours" },
  { key: "minutes", label: "Min" },
  { key: "seconds", label: "Sec" },
];
const PRIZES = [200, 100, 75, 30, 30, 20, 20, 10, 10, 5];
const INITIAL_START = new Date("2026-08-16T00:00:00Z");
const INITIAL_END = new Date("2026-09-18T00:00:00Z");

function getRaceWindow(now = new Date()) {
  let start = new Date(INITIAL_START);
  let end = new Date(INITIAL_END);
  while (now >= end) {
    start = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 16));
    end = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 18));
  }
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

const formatPlace = (place) => {
  if (place % 100 >= 11 && place % 100 <= 13) return `${place}th`;
  if (place % 10 === 1) return `${place}st`;
  if (place % 10 === 2) return `${place}nd`;
  if (place % 10 === 3) return `${place}rd`;
  return `${place}th`;
};

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
        Ranked by how much you&apos;ve wagered — the top ten places receive payouts.
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
        Window {formatUtcDate(countdown.start)} —{" "}
        {formatUtcDate(new Date(countdown.end.getTime() - 1))} · UTC
      </div>

      <div className="leaderboard-prize-block">
        <div className="leaderboard-prize-heading">
          <span>PLACE PAYOUTS</span>
          <span>10 PAID PLACES</span>
        </div>
        <div className="leaderboard-prize-list">
          {PRIZES.map((amount, index) => (
            <div className="leaderboard-prize-item" key={`${index + 1}-${amount}`}>
              <span>{formatPlace(index + 1)}</span>
              <strong>${amount}</strong>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
