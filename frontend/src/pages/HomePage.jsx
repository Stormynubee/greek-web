import Hero from "@/components/Hero";
import FeatureCards from "@/components/FeatureCards";

export default function HomePage() {
  return (
    <>
      <Hero />
      <FeatureCards />

      {/* Legal / disclosure strip */}
      <footer className="bg-black border-t-4 border-[#da291c] py-8 px-4 sm:px-6 mb-14">
        <div className="max-w-[1400px] mx-auto font-inter text-xs opacity-80 space-y-2 text-[#efe9dc]">
          <p><strong className="font-anton uppercase text-[#da291c] tracking-wide">Disclosure:</strong> Links marked with ↗ may be affiliated. Using code GREEK33 supports the channel at no cost to you.</p>
          <p><strong className="font-anton uppercase text-[#da291c] tracking-wide">Responsible Gambling:</strong> Gambling should be entertainment, not income. Never wager money you cannot afford to lose. Free confidential help at 1-800-GAMBLER (US) / BeGambleAware.org (UK).</p>
          <p className="opacity-60">© {new Date().getFullYear()} GreekGodBerry Community · A samurai brutalist experience.</p>
        </div>
      </footer>
    </>
  );
}
