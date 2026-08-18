import { useState } from "react";

const CAT_CREW = [
  {
    name: "Luna",
    note: "The white one",
    accent: "#e8e4d9",
    photos: ["/assets/cat-crew/luna.webp"],
  },
  {
    name: "Peaches",
    note: "Peaches",
    accent: "#f5a45d",
    photos: ["/assets/cat-crew/peaches-1.webp", "/assets/cat-crew/peaches-2.webp"],
  },
  {
    name: "Maki",
    note: "Big Mom",
    accent: "#da291c",
    photos: ["/assets/cat-crew/maki.webp"],
  },
  {
    name: "Maki Junior",
    note: "The one who looks like Mom",
    accent: "#f4c95d",
    photos: ["/assets/cat-crew/maki-junior.webp"],
  },
];

function CrewNames({ compact, activeName, onSelect }) {
  return (
    <div className={compact ? "grid gap-1 mt-3" : "grid grid-cols-2 gap-3 mt-8"}>
      {CAT_CREW.map((cat) => {
        const active = activeName === cat.name;
        const content = (
          <>
            <span
              aria-hidden
              className={compact ? "w-2 h-2 shrink-0" : "w-3 h-3 inline-block mb-2"}
              style={{ backgroundColor: cat.accent }}
            />
            <span className={compact ? "truncate" : "block"}>
              <strong className={compact ? "font-normal" : "font-anton text-lg block"}>{cat.name}</strong>
              {!compact && <span className="font-mono text-[10px] uppercase opacity-65">{cat.note}</span>}
            </span>
          </>
        );

        if (compact) {
          return (
            <div key={cat.name} className="flex items-center gap-2 font-mono text-[10px] uppercase">
              {content}
            </div>
          );
        }

        return (
          <button
            key={cat.name}
            type="button"
            className={`cat-crew-select brutal-border bg-[#171717] p-3 ${active ? "cat-crew-select-active" : ""}`}
            aria-pressed={active}
            onMouseEnter={() => onSelect?.(cat.name, false)}
            onFocus={() => onSelect?.(cat.name, false)}
            onClick={() => onSelect?.(cat.name, true)}
          >
            {content}
          </button>
        );
      })}
    </div>
  );
}

export default function CatCrewReference({ compact = false }) {
  const [activeName, setActiveName] = useState(CAT_CREW[0].name);
  const [photoIndex, setPhotoIndex] = useState(0);
  const activeCat = CAT_CREW.find((cat) => cat.name === activeName) || CAT_CREW[0];

  const selectCat = (name, advance = false) => {
    const nextCat = CAT_CREW.find((cat) => cat.name === name) || CAT_CREW[0];
    if (name !== activeName) {
      setActiveName(name);
      setPhotoIndex(0);
      return;
    }
    if (advance && nextCat.photos.length > 1) {
      setPhotoIndex((current) => (current + 1) % nextCat.photos.length);
    }
  };

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
          <CrewNames activeName={activeName} onSelect={selectCat} />
        </div>

        <figure
          className="cat-preview-panel code-sequence-tilt relative brutal-border-ivory bg-[#171717] p-3 brutal-shadow-red rotate-[1deg]"
          aria-live="polite"
        >
          <div className="absolute -top-3 -left-3 chip chip-red text-[10px] -rotate-3">
            CAT DOSSIER // {activeCat.name}
          </div>
          <img
            key={`${activeCat.name}-${photoIndex}`}
            src={activeCat.photos[photoIndex]}
            alt={`${activeCat.name} cat portrait`}
            width="720"
            height="960"
            loading="lazy"
            decoding="async"
            className="cat-preview-image w-full max-h-[560px] object-cover object-top"
          />
          <figcaption className="font-mono text-[10px] uppercase tracking-wide mt-3 text-[#efe9dc]/60 flex flex-wrap justify-between gap-2">
            <span>{activeCat.name} · {activeCat.note}</span>
            {activeCat.photos.length > 1 && (
              <span>PHOTO {photoIndex + 1}/{activeCat.photos.length} · TAP NAME TO CYCLE</span>
            )}
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
