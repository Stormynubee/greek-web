const CAT_CREW = [
  { name: "Luna", note: "The white one", accent: "#e8e4d9" },
  { name: "Peaches", note: "The orange-haired one", accent: "#f5a45d" },
  { name: "Maki", note: "Big Mom", accent: "#da291c" },
  { name: "Maki Junior", note: "The one who looks like Mom", accent: "#f4c95d" },
];

function CrewNames({ compact }) {
  return (
    <div className={compact ? "grid gap-1 mt-3" : "grid grid-cols-2 gap-3 mt-8"}>
      {CAT_CREW.map((cat) => (
        <div
          key={cat.name}
          className={compact
            ? "flex items-center gap-2 font-mono text-[10px] uppercase"
            : "brutal-border bg-[#171717] p-3"}
        >
          <span
            aria-hidden
            className={compact ? "w-2 h-2 shrink-0" : "w-3 h-3 inline-block mb-2"}
            style={{ backgroundColor: cat.accent }}
          />
          <span className={compact ? "truncate" : "block"}>
            <strong className={compact ? "font-normal" : "font-anton text-lg block"}>{cat.name}</strong>
            {!compact && <span className="font-mono text-[10px] uppercase opacity-65">{cat.note}</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function CatCrewReference({ compact = false }) {
  if (compact) {
    return (
      <aside
        data-testid="cat-crew-admin-reference"
        className="brutal-border-ivory bg-black p-2 flex items-center gap-3 max-w-[280px]"
        aria-label="Client cat reference"
      >
        <img
          src="/assets/cat-crew-reference.png"
          alt="Client-provided cat portrait reference"
          width="72"
          height="96"
          loading="lazy"
          decoding="async"
          className="w-[72px] h-24 object-cover object-top border-2 border-[#efe9dc]/30 shrink-0"
        />
        <div className="min-w-0">
          <div className="font-mono text-[9px] uppercase tracking-widest text-[#f4c95d]">Client reference</div>
          <div className="font-anton uppercase text-xl leading-none mt-1">Cat Council</div>
          <CrewNames compact />
        </div>
      </aside>
    );
  }

  return (
    <section
      data-testid="cat-crew-reference"
      className="bg-[#0a0a0a] text-[#efe9dc] py-16 px-4 sm:px-6 border-t-4 border-[#da291c]"
    >
      <div className="code-sequence max-w-[1400px] mx-auto grid md:grid-cols-[1.1fr_0.9fr] gap-8 items-center">
        <div>
          <div className="chip chip-red mb-3">CLIENT LORE · THE CAT COUNCIL</div>
          <h2 className="font-anton uppercase text-5xl sm:text-7xl leading-[0.88] tracking-tight">
            Meet the <span className="text-[#da291c]">Crew</span>
          </h2>
          <p className="font-inter max-w-xl mt-5 text-base sm:text-lg leading-relaxed text-[#efe9dc]/80">
            A small piece of home base, brought into the arena. Four names, one
            family, and enough personality to run the whole server.
          </p>
          <CrewNames />
        </div>

        <figure className="code-sequence-tilt relative brutal-border-ivory bg-[#171717] p-3 brutal-shadow-red rotate-[1deg]">
          <div className="absolute -top-3 -left-3 chip chip-red text-[10px] -rotate-3">REFERENCE PHOTO</div>
          <img
            src="/assets/cat-crew-reference.png"
            alt="Client-provided cat portrait reference for the Cat Council"
            width="768"
            height="1024"
            loading="lazy"
            decoding="async"
            className="w-full max-h-[560px] object-cover object-top"
          />
          <figcaption className="font-mono text-[10px] uppercase tracking-wide mt-3 text-[#efe9dc]/60">
            Luna · Peaches · Maki · Maki Junior
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
