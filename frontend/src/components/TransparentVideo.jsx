import { useEffect, useRef } from "react";

const GREEN_KEY = { r: 0, g: 160, b: 60 };
const GHOST_PLAYBACK_RATE = 0.65;

export default function TransparentVideo({ src, className, style, motion, ...props }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return undefined;

    const context = canvas.getContext("2d", { willReadFrequently: true });
    let animationFrame;
    let width = 0;
    let height = 0;

    const draw = () => {
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA && width && height) {
        context.drawImage(video, 0, 0, width, height);
        const frame = context.getImageData(0, 0, width, height);
        const pixels = frame.data;

        for (let i = 0; i < pixels.length; i += 4) {
          const red = pixels[i];
          const green = pixels[i + 1];
          const blue = pixels[i + 2];
          const greenStrength = green - Math.max(red, blue);
          const distance =
            Math.abs(red - GREEN_KEY.r) +
            Math.abs(green - GREEN_KEY.g) +
            Math.abs(blue - GREEN_KEY.b);

          if (greenStrength > 24 && distance < 220) {
            pixels[i + 3] = 0;
          } else if (greenStrength > 8 && distance < 300) {
            pixels[i + 3] = Math.max(0, Math.round((greenStrength - 8) * 12));
          }
        }

        context.putImageData(frame, 0, 0);

        if (motion === "ghost") {
          const elapsed = video.currentTime % 10;
          const displayWidth = canvas.getBoundingClientRect().width || 360;
          const startX = displayWidth * -0.35;
          const endX = window.innerWidth - displayWidth;
          const progress = elapsed <= 5
            ? elapsed / 5
            : elapsed <= 6
              ? 1
              : 1 - ((elapsed - 6) / 4);
          const x = startX + (endX - startX) * progress;
          canvas.style.transform = `translateX(${x}px)`;
        }
      }
      animationFrame = requestAnimationFrame(draw);
    };

    const resize = () => {
      width = video.videoWidth || 854;
      height = video.videoHeight || 480;
      canvas.width = width;
      canvas.height = height;
    };

    video.addEventListener("loadedmetadata", resize);
    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) resize();
    video.playbackRate = motion === "ghost" ? GHOST_PLAYBACK_RATE : 1;
    video.play().catch(() => {});
    animationFrame = requestAnimationFrame(draw);

    return () => {
      video.removeEventListener("loadedmetadata", resize);
      cancelAnimationFrame(animationFrame);
    };
  }, [motion, src]);

  return (
    <>
      <video
        ref={videoRef}
        src={src}
        autoPlay
        muted
        loop
        playsInline
        preload="auto"
        aria-hidden
        className="absolute w-px h-px opacity-0 pointer-events-none"
        {...props}
      />
      <canvas ref={canvasRef} aria-hidden className={className} style={style} />
    </>
  );
}
