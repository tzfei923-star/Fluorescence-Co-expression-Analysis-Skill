#!/usr/bin/env python3
"""
Fluorescence Co-expression Analysis Tool
Standalone script for analyzing two-channel fluorescence microscopy images.
Supports CZI (Zeiss), TIFF, and JPEG formats.
"""

import struct
import argparse
import json
from pathlib import Path
from typing import Dict, Tuple, Optional
import numpy as np
from PIL import Image
from skimage.filters import threshold_otsu


class FluorescenceAnalyzer:
    """Analyzes pixel-level co-expression in two-channel fluorescence images."""

    def __init__(self, sox2_path: str, gfp_path: str, output_dir: str = "output"):
        """
        Initialize analyzer with two channel images.

        Args:
            sox2_path: Path to SOX2 channel image (magenta/R channel)
            gfp_path: Path to GFP channel image (green/G channel)
            output_dir: Directory to save results
        """
        self.sox2_path = Path(sox2_path)
        self.gfp_path = Path(gfp_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.sox2: Optional[np.ndarray] = None
        self.gfp: Optional[np.ndarray] = None
        self.sox2_format: Optional[str] = None
        self.gfp_format: Optional[str] = None

    @staticmethod
    def load_czi_channels(path: str) -> Dict[int, np.ndarray]:
        """
        Load channels from Zeiss CZI raw image file.

        Args:
            path: Path to CZI file

        Returns:
            Dictionary mapping channel index to 16-bit numpy array
        """
        print(f"  Parsing CZI: {path}")
        with open(path, "rb") as f:
            raw = f.read()

        segments = []
        pos = 0
        while pos < len(raw) - 32:
            seg_id = raw[pos : pos + 16].rstrip(b"\x00").decode("ascii", errors="ignore")
            if seg_id in [
                "ZISRAWFILE",
                "ZISRAWMETADATA",
                "ZISRAWSUBBLOCK",
                "ZISRAWDIRECTORY",
                "ZISRAWATTDIR",
                "ZISRAWATTACHMENT",
            ]:
                alloc = struct.unpack_from("<q", raw, pos + 16)[0]
                segments.append((pos, seg_id, alloc))
                pos += 32 + alloc
            else:
                pos += 1

        imgs = {}
        for pos, sid, alloc in segments:
            if sid != "ZISRAWSUBBLOCK":
                continue
            sb_start = pos + 32
            meta_size = struct.unpack_from("<i", raw, sb_start)[0]
            dir_start = sb_start + 16
            dir_size = struct.unpack_from("<i", raw, dir_start)[0]
            dim_count = struct.unpack_from("<i", raw, dir_start + 28)[0]

            ch_idx = 0
            sx = 465
            sy = 465
            for d in range(dim_count):
                doff = dir_start + 32 + d * 20
                dn = raw[doff : doff + 4].rstrip(b"\x00").decode("ascii", "ignore")
                val = struct.unpack_from("<i", raw, doff + 4)[0]
                sz = struct.unpack_from("<i", raw, doff + 8)[0]
                if dn == "C":
                    ch_idx = val
                if dn == "X":
                    sx = sz
                if dn == "Y":
                    sy = sz

            data_offset = dir_start + dir_size + meta_size
            avail = len(raw) - data_offset
            npx = sx * sy

            if avail >= npx * 2:
                arr = np.frombuffer(
                    raw[data_offset : data_offset + npx * 2], dtype=np.uint16
                ).reshape(sy, sx).copy()
            else:
                buf = bytearray(npx * 2)
                buf[:avail] = raw[data_offset : data_offset + avail]
                arr = np.frombuffer(bytes(buf), dtype=np.uint16).reshape(sy, sx).copy()

            imgs[ch_idx] = arr
            print(f"    Channel {ch_idx}: {sy}×{sx} (16-bit), {avail} bytes available")

        return imgs

    @staticmethod
    def load_tiff_channel(path: str, rgb_idx: int = 0) -> Tuple[np.ndarray, str]:
        """
        Load single-channel TIFF (typically 8-bit ZEN export).

        Args:
            path: Path to TIFF file
            rgb_idx: RGB channel index (0=R/SOX2, 1=G/GFP, 2=B)

        Returns:
            Tuple of (array, format string)
        """
        print(f"  Loading TIFF: {path} (channel {rgb_idx})")
        arr = np.array(Image.open(path).convert("RGB"))
        channel_arr = arr[:, :, rgb_idx].astype(np.float32)
        print(f"    Size: {arr.shape[0]}×{arr.shape[1]}, 8-bit")
        return channel_arr, "TIFF"

    @staticmethod
    def load_jpg_channel(path: str, rgb_idx: int = 0) -> Tuple[np.ndarray, str]:
        """
        Load single RGB channel from JPEG.

        Args:
            path: Path to JPEG file
            rgb_idx: RGB channel index (0=R/SOX2, 1=G/GFP, 2=B)

        Returns:
            Tuple of (array, format string)
        """
        print(f"  Loading JPEG: {path} (channel {rgb_idx})")
        arr = np.array(Image.open(path).convert("RGB"))
        channel_arr = arr[:, :, rgb_idx].astype(np.float32)
        print(f"    Size: {arr.shape[0]}×{arr.shape[1]}, 8-bit")
        return channel_arr, "JPEG"

    def load_channels(self) -> None:
        """Auto-detect format and load both channels."""
        print(f"\n📷 Loading images...")

        # Load SOX2 (R channel)
        sox2_suffix = self.sox2_path.suffix.lower()
        if sox2_suffix == ".czi":
            czi_data = self.load_czi_channels(str(self.sox2_path))
            self.sox2 = czi_data.get(0, list(czi_data.values())[0]).astype(np.float32)
            self.sox2_format = "CZI"
        elif sox2_suffix in [".tif", ".tiff"]:
            self.sox2, self.sox2_format = self.load_tiff_channel(
                str(self.sox2_path), rgb_idx=0
            )
        elif sox2_suffix in [".jpg", ".jpeg"]:
            self.sox2, self.sox2_format = self.load_jpg_channel(
                str(self.sox2_path), rgb_idx=0
            )
        else:
            raise ValueError(f"Unsupported format: {sox2_suffix}")

        # Load GFP (G channel)
        gfp_suffix = self.gfp_path.suffix.lower()
        if gfp_suffix == ".czi":
            czi_data = self.load_czi_channels(str(self.gfp_path))
            self.gfp = czi_data.get(1, list(czi_data.values())[-1]).astype(np.float32)
            self.gfp_format = "CZI"
        elif gfp_suffix in [".tif", ".tiff"]:
            self.gfp, self.gfp_format = self.load_tiff_channel(
                str(self.gfp_path), rgb_idx=1
            )
        elif gfp_suffix in [".jpg", ".jpeg"]:
            self.gfp, self.gfp_format = self.load_jpg_channel(
                str(self.gfp_path), rgb_idx=1
            )
        else:
            raise ValueError(f"Unsupported format: {gfp_suffix}")

    @staticmethod
    def get_threshold(
        arr: np.ndarray, method: str = "otsu"
    ) -> Tuple[float, str]:
        """
        Select threshold based on signal distribution.

        Args:
            arr: Image array
            method: "otsu", "mean2sd", or "p80"

        Returns:
            Tuple of (threshold value, description)
        """
        if method == "otsu":
            th = threshold_otsu(arr.astype(np.uint8))
            return float(th), "Otsu"
        elif method == "mean2sd":
            th = arr.mean() + 2 * arr.std()
            return float(th), "mean + 2SD"
        elif method == "p80":
            th = np.percentile(arr, 80)
            return float(th), f"p80 ({th:.1f})"
        else:
            raise ValueError(f"Unknown method: {method}")

    def analyze(
        self,
        sox2_method: str = "otsu",
        gfp_method: str = "mean2sd",
        verbose: bool = True,
    ) -> Dict:
        """
        Perform co-expression analysis.

        Args:
            sox2_method: Threshold method for SOX2
            gfp_method: Threshold method for GFP
            verbose: Print detailed output

        Returns:
            Dictionary with analysis results
        """
        if self.sox2 is None or self.gfp is None:
            self.load_channels()

        if verbose:
            print(f"\n📊 Analyzing co-expression...")

        # Get thresholds
        sox2_th, sox2_method_name = self.get_threshold(self.sox2, sox2_method)
        gfp_th, gfp_method_name = self.get_threshold(self.gfp, gfp_method)

        if verbose:
            print(f"  SOX2 threshold ({sox2_method_name}): {sox2_th:.1f}")
            print(f"  GFP threshold ({gfp_method_name}): {gfp_th:.1f}")

        # Create masks
        sox2_mask = self.sox2 > sox2_th
        gfp_mask = self.gfp > gfp_th
        coexp = sox2_mask & gfp_mask

        # Calculate statistics
        total_px = self.sox2.size
        sox2_px = int(sox2_mask.sum())
        gfp_px = int(gfp_mask.sum())
        coexp_px = int(coexp.sum())

        sox2_pct = 100 * sox2_px / total_px
        gfp_pct = 100 * gfp_px / total_px
        coexp_pct = 100 * coexp_px / total_px
        coexp_of_gfp = 100 * coexp_px / max(gfp_px, 1)
        coexp_of_sox2 = 100 * coexp_px / max(sox2_px, 1)

        results = {
            "image_size": {"width": self.sox2.shape[1], "height": self.sox2.shape[0]},
            "total_pixels": int(total_px),
            "sox2": {
                "format": self.sox2_format,
                "threshold_method": sox2_method_name,
                "threshold_value": float(sox2_th),
                "positive_pixels": sox2_px,
                "positive_percent": round(sox2_pct, 1),
                "mean_intensity": float(self.sox2.mean()),
                "std_intensity": float(self.sox2.std()),
            },
            "gfp": {
                "format": self.gfp_format,
                "threshold_method": gfp_method_name,
                "threshold_value": float(gfp_th),
                "positive_pixels": gfp_px,
                "positive_percent": round(gfp_pct, 1),
                "mean_intensity": float(self.gfp.mean()),
                "std_intensity": float(self.gfp.std()),
            },
            "coexpression": {
                "coexp_pixels": coexp_px,
                "coexp_percent_of_total": round(coexp_pct, 1),
                "coexp_percent_of_gfp": round(coexp_of_gfp, 1),
                "coexp_percent_of_sox2": round(coexp_of_sox2, 1),
            },
        }

        if verbose:
            print(f"\n✅ Results:")
            print(f"  SOX2+ area: {sox2_pct:.1f}% ({sox2_px:,} pixels)")
            print(f"  GFP+ area: {gfp_pct:.1f}% ({gfp_px:,} pixels)")
            print(
                f"  Co-expression: {coexp_pct:.1f}% ({coexp_px:,} pixels)"
            )
            print(
                f"  📌 Co-exp / GFP+ (primary metric): {coexp_of_gfp:.1f}%"
            )
            print(
                f"  Co-exp / SOX2+ (secondary metric): {coexp_of_sox2:.1f}%"
            )

        return results, sox2_mask, gfp_mask, coexp

    def save_visualizations(
        self, sox2_mask: np.ndarray, gfp_mask: np.ndarray, coexp: np.ndarray
    ) -> None:
        """
        Generate and save visualization images.

        Args:
            sox2_mask: SOX2 binary mask
            gfp_mask: GFP binary mask
            coexp: Co-expression binary mask
        """
        print(f"\n🎨 Generating visualizations...")

        def autonorm(a, lo=1, hi=99):
            mn = np.percentile(a, lo)
            mx = np.percentile(a, hi)
            return np.clip((a - mn) / max(mx - mn, 1) * 255, 0, 255).astype(
                np.uint8
            )

        s = autonorm(self.sox2)
        g = autonorm(self.gfp)
        h, w = s.shape

        # Composite: SOX2=magenta(R+B), GFP=green(G)
        composite = np.stack([s, g, s], axis=2)

        # Mask overlay
        mask = np.zeros((h, w, 3), dtype=np.uint8)
        mask[sox2_mask & ~gfp_mask] = [220, 0, 220]  # SOX2 only = magenta
        mask[gfp_mask & ~sox2_mask] = [0, 220, 0]  # GFP only = green
        mask[coexp] = [255, 255, 0]  # Co-expression = yellow

        blend = (
            (composite.astype(float) * 0.4 + mask.astype(float) * 0.6)
            .clip(0, 255)
            .astype(np.uint8)
        )

        # Save images
        Image.fromarray(composite).save(self.output_dir / "composite.png")
        Image.fromarray(mask).save(self.output_dir / "mask.png")
        Image.fromarray(blend).save(self.output_dir / "analysis.png")

        print(f"  ✓ Saved: composite.png, mask.png, analysis.png")

    def save_results_json(self, results: Dict, filename: str = "results.json") -> None:
        """Save analysis results to JSON."""
        with open(self.output_dir / filename, "w") as f:
            json.dump(results, f, indent=2)
        print(f"  ✓ Saved: {filename}")

    def run(
        self,
        sox2_method: str = "otsu",
        gfp_method: str = "mean2sd",
        save_viz: bool = True,
    ) -> Dict:
        """
        Run complete analysis pipeline.

        Args:
            sox2_method: Threshold method for SOX2
            gfp_method: Threshold method for GFP
            save_viz: Save visualization images

        Returns:
            Analysis results dictionary
        """
        self.load_channels()
        results, sox2_mask, gfp_mask, coexp = self.analyze(
            sox2_method, gfp_method, verbose=True
        )

        if save_viz:
            self.save_visualizations(sox2_mask, gfp_mask, coexp)

        self.save_results_json(results)
        print(f"\n✨ Analysis complete. Results saved to: {self.output_dir}/")
        return results


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(
        description="Fluorescence Co-expression Analysis Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis with default thresholds
  python fluorescence_analysis.py sox2.tif gfp.tif

  # CZI files
  python fluorescence_analysis.py image_c0.czi image_c1.czi -o results/

  # Custom thresholds
  python fluorescence_analysis.py sox2.tif gfp.tif \\
    --sox2-method otsu --gfp-method p80

  # Without visualizations
  python fluorescence_analysis.py sox2.tif gfp.tif --no-viz
        """,
    )

    parser.add_argument("sox2_path", help="Path to SOX2 channel image")
    parser.add_argument("gfp_path", help="Path to GFP channel image")
    parser.add_argument(
        "-o",
        "--output",
        default="output",
        help="Output directory (default: output)",
    )
    parser.add_argument(
        "--sox2-method",
        choices=["otsu", "mean2sd", "p80"],
        default="otsu",
        help="Threshold method for SOX2 (default: otsu)",
    )
    parser.add_argument(
        "--gfp-method",
        choices=["otsu", "mean2sd", "p80"],
        default="mean2sd",
        help="Threshold method for GFP (default: mean2sd)",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Skip visualization generation",
    )

    args = parser.parse_args()

    # Run analysis
    analyzer = FluorescenceAnalyzer(args.sox2_path, args.gfp_path, args.output)
    analyzer.run(
        sox2_method=args.sox2_method,
        gfp_method=args.gfp_method,
        save_viz=not args.no_viz,
    )


if __name__ == "__main__":
    main()
