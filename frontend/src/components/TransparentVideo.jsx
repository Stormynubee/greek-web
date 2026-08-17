import { useEffect, useRef } from "react";

const GREEN_KEY = { r: 0, g: 160, b: 60 };
const GHOST_PLAYBACK_RATE = 0.5;

export default function TransparentVideo({
  src,
  className,
  style,
  motion,
  motionBounds = "full",
  interactive = false,
  onClick,
  onEdgeChange,
  ariaLabel,
  ...videoProps
}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const edgeChangeRef = useRef(null);
  const lastEdgeRef = useRef(null);

  useEffect(() => {
    edgeChangeRef.current = onEdgeChange;
  }, [onEdgeChange]);

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return undefined;

    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) return undefined;
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    let reducedMotion = motionPreference.matches;
    const frameInterval = 1000 / 30;
    const maxDevicePixelRatio = 1.5;
    let frameRequest;
    let animationFrame;
    let resizeObserver;
    let visible = true;
    let lastFrameAt = 0;
    let width = 0;
    let height = 0;
    let active = true;

    const cancelFrame = () => {
      if (frameRequest !== undefined) {
        if (video.cancelVideoFrameCallback) {
          video.cancelVideoFrameCallback(frameRequest);
        }
        frameRequest = undefined;
      }
      if (animationFrame !== undefined) {
        cancelAnimationFrame(animationFrame);
        animationFrame = undefined;
      }
    };

    const resize = () => {
      const sourceWidth = video.videoWidth || 854;
      const sourceHeight = video.videoHeight || 480;
      const displayWidth = canvas.getBoundingClientRect().width || 360;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, maxDevicePixelRatio);
      const renderWidth = Math.max(
        1,
        Math.min(sourceWidth, Math.round(displayWidth * pixelRatio))
      );
      const renderHeight = Math.max(1, Math.round(renderWidth * sourceHeight / sourceWidth));

      if (renderWidth === width && renderHeight === height) return;
      width = renderWidth;
      height = renderHeight;
      canvas.width = width;
      canvas.height = height;
    };

    const draw = () => {
      if (
        !active ||
        !visible ||
        video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
        !width ||
        !height
      ) {
        return;
      }

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
        const isCornerMotion = motionBounds === "corner";
        const maxX = Math.max(0, window.innerWidth - displayWidth - (isCornerMotion ? 16 : 0));
        const startX = isCornerMotion
          ? Math.min(maxX, Math.max(0, window.innerWidth * 0.58))
          : displayWidth * -0.35;
        const endX = isCornerMotion ? maxX : window.innerWidth - displayWidth;
        const travelDuration = isCornerMotion ? 6 : 5;
        const pauseDuration = 1;
        const progress = elapsed <= travelDuration
          ? elapsed / travelDuration
          : elapsed <= travelDuration + pauseDuration
            ? 1
            : 1 - ((elapsed - travelDuration - pauseDuration) / (10 - travelDuration - pauseDuration));
        const x = startX + (endX - startX) * progress;
        canvas.style.transform = `translateX(${x}px)`;
        const edge = isCornerMotion
          ? (progress <= 0.02 || progress >= 0.98 ? "right" : null)
          : (progress <= 0.02 ? "left" : progress >= 0.98 ? "right" : null);
        if (edge !== lastEdgeRef.current) {
          lastEdgeRef.current = edge;
          edgeChangeRef.current?.(edge);
        }
      }
    };

    const scheduleFrame = () => {
      if (
        !active ||
        !visible ||
        reducedMotion ||
        frameRequest !== undefined ||
        animationFrame !== undefined
      ) return;
      if (typeof video.requestVideoFrameCallback === "function") {
        frameRequest = video.requestVideoFrameCallback(() => {
          frameRequest = undefined;
          draw();
          scheduleFrame();
        });
        return;
      }

      animationFrame = requestAnimationFrame((now) => {
        animationFrame = undefined;
        if (now - lastFrameAt >= frameInterval) {
          lastFrameAt = now;
          draw();
        }
        scheduleFrame();
      });
    };

    const syncPlayback = () => {
      if (!active) return;
      if (reducedMotion || !visible || document.visibilityState !== "visible") {
        video.pause();
        cancelFrame();
        if (reducedMotion && video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
          draw();
        }
        return;
      }
      video.play().catch(() => {});
      scheduleFrame();
    };

    const handleVisibility = () => syncPlayback();
    const handleMotionPreference = () => {
      reducedMotion = motionPreference.matches;
      syncPlayback();
    };
    const handleLoadedData = () => {
      resize();
      if (reducedMotion) draw();
      else syncPlayback();
    };

    const observer = typeof IntersectionObserver === "function"
      ? new IntersectionObserver(([entry]) => {
        visible = entry.isIntersecting;
        syncPlayback();
      }, { threshold: 0.01 })
      : null;

    video.addEventListener("loadedmetadata", resize);
    video.addEventListener("loadeddata", handleLoadedData);
    document.addEventListener("visibilitychange", handleVisibility);
    motionPreference.addEventListener?.("change", handleMotionPreference);
    observer?.observe(canvas);
    resizeObserver = typeof ResizeObserver === "function"
      ? new ResizeObserver(resize)
      : null;
    resizeObserver?.observe(canvas);

    if (video.readyState >= HTMLMediaElement.HAVE_METADATA) resize();
    video.playbackRate = motion === "ghost" ? GHOST_PLAYBACK_RATE : 1;
    syncPlayback();

    return () => {
      active = false;
      video.removeEventListener("loadedmetadata", resize);
      video.removeEventListener("loadeddata", handleLoadedData);
      document.removeEventListener("visibilitychange", handleVisibility);
      motionPreference.removeEventListener?.("change", handleMotionPreference);
      observer?.disconnect();
      resizeObserver?.disconnect();
      cancelFrame();
      video.pause();
    };
  }, [motion, motionBounds, src]);

  return (
    <>
      <video
        ref={videoRef}
        src={src}
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        aria-hidden
        className="absolute w-px h-px opacity-0 pointer-events-none"
        {...videoProps}
      />
      <canvas
        ref={canvasRef}
        aria-label={ariaLabel}
        aria-hidden={!interactive}
        className={`${className || ""}${interactive ? " ghost-canvas-interactive" : ""}`}
        style={style}
        onClick={onClick}
        onKeyDown={(event) => {
          if (interactive && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            onClick?.(event);
          }
        }}
        role={interactive ? "button" : undefined}
        tabIndex={interactive ? 0 : undefined}
      />
    </>
  );
}
