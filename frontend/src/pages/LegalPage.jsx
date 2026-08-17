const externalLinks = [
  { label: "Kick", href: "https://kick.com/greekgodberry" },
  { label: "Twitch", href: "https://www.twitch.tv/greekgodberry" },
  { label: "YouTube", href: "https://www.youtube.com/@greekgodberry" },
  { label: "Instagram", href: "https://www.instagram.com/greekgodberry/?hl=en" },
  { label: "X / Twitter", href: "https://x.com/greekgodberryx" },
  { label: "Discord", href: "https://discord.gg/quEGjqWrT" },
];

export default function LegalPage() {
  return (
    <section className="min-h-screen bg-[#efe9dc] text-black py-10 px-4 sm:px-6 pb-24">
      <div className="code-sequence max-w-4xl mx-auto">
        <div className="chip chip-red mb-3">DISCLOSURES · 18+</div>
        <h1 className="font-anton uppercase text-5xl sm:text-7xl leading-none tracking-tight">
          Legal <span className="text-[#da291c]">Codex</span>
        </h1>

        <div className="mt-8 grid gap-4">
          <article className="brutal-border brutal-shadow bg-white p-5">
            <h2 className="font-anton uppercase text-2xl">Responsible Gambling</h2>
            <p className="font-inter mt-2 leading-relaxed">
              GreekGodBerry is an entertainment community. Gambling should never be
              treated as income. Only wager what you can afford to lose, and take a
              break if it stops being fun. In the US, call 1-800-GAMBLER for free,
              confidential support.
            </p>
          </article>

          <article className="brutal-border brutal-shadow bg-black text-[#efe9dc] p-5">
            <h2 className="font-anton uppercase text-2xl text-[#da291c]">Affiliate Disclosure</h2>
            <p className="font-inter mt-2 leading-relaxed">
              Some links may be sponsored or affiliate links. Using code GREEK33 may
              support the channel at no additional cost to you.
            </p>
          </article>

          <article className="brutal-border brutal-shadow bg-white p-5">
            <h2 className="font-anton uppercase text-2xl">Official Channels</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {externalLinks.map((link) => (
                <a
                  key={link.label}
                  href={link.href}
                  target="_blank"
                  rel="noreferrer"
                  className="chip hover:!bg-black hover:!text-[#efe9dc] transition-colors"
                >
                  {link.label} ↗
                </a>
              ))}
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
