# app/tasks/tod.py
import contextlib
import logging
import math
import re
import xml.dom.minidom
import xml.etree.ElementTree as ET
from pathlib import Path

from app.data.ce_params import LEGACY_MAP, ORDERED_PARAMS


class TimeOfDayConverter:
    """
    Task to convert legacy CryEngine (CE3/CE4) TimeOfDay XML files
    to the newer CryEngine 5 format (.env + .xml presets).
    """

    class Key:
        def __init__(self, time, value, flags=0):
            self.time = float(time)
            self.flags = int(flags)
            self.value = [float(v) for v in value] if isinstance(value, list) else float(value)

    class Spline:
        def __init__(self):
            self.keys = []

        def add_key(self, time, value, flags=0):
            self.keys.append(TimeOfDayConverter.Key(time, value, flags))
            self.keys.sort(key=lambda x: x.time)

        def evaluate(self, t):
            if not self.keys:
                return 0.0
            t = t % 1.0
            if len(self.keys) == 1:
                return self.keys[0].value

            prev = self.keys[-1]
            next_k = self.keys[0]

            # Find correct interval
            if t < self.keys[0].time:
                prev = self.keys[-1]
                next_k = self.keys[0]
                t_adj = t + 1.0
                next_time = next_k.time + 1.0
            elif t >= self.keys[-1].time:
                prev = self.keys[-1]
                next_k = self.keys[0]
                t_adj = t
                next_time = next_k.time + 1.0
            else:
                t_adj = t
                for i in range(len(self.keys) - 1):
                    if t >= self.keys[i].time and t < self.keys[i + 1].time:
                        prev = self.keys[i]
                        next_k = self.keys[i + 1]
                        break
                next_time = next_k.time

            prev_time = prev.time

            diff = next_time - prev_time
            ratio = 0 if diff <= 1e-6 else (t_adj - prev_time) / diff

            if isinstance(prev.value, list):
                return [prev.value[i] + (next_k.value[i] - prev.value[i]) * ratio for i in range(3)]
            else:
                return prev.value + (next_k.value - prev.value) * ratio

    TIME_SCALE = 144000.0
    FALLBACK_SUN_INTENSITY_SCALAR = 50000.0
    HDR_DYNAMIC_MULTIPLIER = 1.0

    def __init__(self, signals):
        self.signals = signals

    def _format_ce5_key(self, time_norm, value, flags):
        time_tick = round(float(time_norm) * self.TIME_SCALE)

        if math.isnan(value) or math.isinf(value):
            value = 0.0

        # Strict formatting to avoid scientific notation
        val_str = f"{value:.6f}"
        val_str = val_str.rstrip("0").rstrip(".") if "." in val_str else val_str
        if val_str == "":
            val_str = "0"

        # Force linear interpolation flag (1) for safety
        return f"{time_tick}:{val_str}:0:0:0:0:1:1:0"

    def _parse_float_spline(self, keys_str):
        s = self.Spline()
        if not keys_str:
            return s

        for item in keys_str.strip().strip(",").split(","):
            parts = item.split(":")
            if len(parts) >= 2:
                with contextlib.suppress(ValueError, IndexError):
                    s.add_key(float(parts[0]), float(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
        return s

    def _parse_color_spline(self, keys_str):
        s = self.Spline()
        matches = re.findall(r"([\d\.]+):\(([\d\.]+):([\d\.]+):([\d\.]+)\):?(\d*)", keys_str)
        for m in matches:
            with contextlib.suppress(ValueError, IndexError):
                s.add_key(float(m[0]), [float(m[1]), float(m[2]), float(m[3])], int(m[4]) if m[4] else 0)
        return s

    def _calculate_fallback_sun(self, splines):
        sun_color = splines.get("Sun color", self.Spline())
        if not sun_color.keys:
            sun_color.add_key(0, [1, 1, 1])

        sun_mult = splines.get("Sun color multiplier", self.Spline())
        if not sun_mult.keys:
            sun_mult.add_key(0, 1)

        hdr_pow = splines.get("HDR dynamic power factor", self.Spline())
        if not hdr_pow.keys:
            hdr_pow.add_key(0, 0)

        new_s = self.Spline()
        times = (
            set(k.time for k in sun_color.keys) | set(k.time for k in sun_mult.keys) | set(k.time for k in hdr_pow.keys)
        )

        for t in sorted(list(times)) or [0.0, 1.0]:
            c = sun_color.evaluate(t)
            m = sun_mult.evaluate(t)
            hdr = hdr_pow.evaluate(t)

            hdr_mult = math.pow(self.HDR_DYNAMIC_MULTIPLIER, hdr)
            lum = c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722
            final = min(m * lum * hdr_mult * self.FALLBACK_SUN_INTENSITY_SCALAR, 550000.0)

            new_s.add_key(t, final, 1)

        return new_s

    def _pretty_print_xml(self, elem):
        xml_str = ET.tostring(elem, encoding="unicode")
        pretty = xml.dom.minidom.parseString(xml_str).toprettyxml(indent=" ")
        # Remove potentially duplicate xml declaration
        if pretty.startswith("<?xml"):
            parts = pretty.split("\n", 1)
            if len(parts) > 1:
                return parts[1]
        return pretty

    def _add_constants_block(self, env_preset):
        consts = ET.SubElement(env_preset, "Constants")
        ET.SubElement(consts, "Sun", {"Latitude": "240", "Longitude": "90", "SunLinkedToTOD": "true"})
        ET.SubElement(
            consts,
            "Moon",
            {
                "Latitude": "240",
                "Longitude": "45",
                "Size": "0.5",
                "Texture": "%ENGINE%/EngineAssets/Textures/Skys/Night/half_moon.dds",
            },
        )
        ET.SubElement(consts, "Sky", {"MaterialDef": "", "MaterialLow": ""})
        # Add minimal required constants
        wind = ET.SubElement(consts, "Wind", {"BreezeEnabled": "false"})
        ET.SubElement(wind, "WindVector", {"x": "1", "y": "0", "z": "0"})

    def run(self, input_file: Path) -> dict:
        logging.info(f"Converting TimeOfDay: {input_file.name}")
        try:
            content = input_file.read_text(encoding="latin-1", errors="ignore")
            content_stripped = content.strip()

            if (
                not content_stripped.startswith("<Root>")
                and not content_stripped.startswith("<TimeOfDay")
                and content_stripped.startswith("<Variable")
            ):
                content = f"<Root>{content}</Root>"

            try:
                root = ET.fromstring(content)
            except Exception:
                root = ET.fromstring(f"<Root>{content}</Root>")

            parsed_splines = {}
            for v in root.findall(".//Variable"):
                name = v.get("Name")
                if not name:
                    continue

                spline_node = v.find("Spline")
                keys = spline_node.get("Keys", "") if spline_node is not None else ""

                if "(" in keys and ")" in keys:
                    parsed_splines[name] = self._parse_color_spline(keys)
                else:
                    parsed_splines[name] = self._parse_float_spline(keys)

            has_sun = "Sun intensity" in parsed_splines
            if not has_sun:
                parsed_splines["Sun intensity"] = self._calculate_fallback_sun(parsed_splines)

            env_root = ET.Element("EnvironmentPreset", {"CryXmlVersion": "2", "version": "4"})

            for pid, ptype, pmin, pmax in ORDERED_PARAMS:
                current_spline = None

                # Mapping logic
                found_key = None
                for legacy_key, new_id in LEGACY_MAP.items():
                    if new_id == pid:
                        found_key = legacy_key
                        break

                if pid == "PARAM_SUN_INTENSITY":
                    if has_sun:
                        current_spline = parsed_splines.get("Sun intensity")
                    else:
                        current_spline = parsed_splines.get("Sun intensity")  # Already calculated
                elif found_key and found_key in parsed_splines:
                    current_spline = parsed_splines[found_key]

                # Create XML Node
                var_node = ET.SubElement(env_root, "var", id=pid, type=ptype, minValue=str(pmin), maxValue=str(pmax))

                if current_spline and current_spline.keys:
                    # Clean and sort logic is implicitly handled by Spline.add_key sorting

                    if ptype == "TYPE_COLOR":
                        k_r, k_g, k_b = [], [], []
                        for k in current_spline.keys:
                            val = k.value
                            if isinstance(val, float):
                                val = [val, val, val]

                            safe_r = max(0.0, min(100.0, val[0]))
                            safe_g = max(0.0, min(100.0, val[1]))
                            safe_b = max(0.0, min(100.0, val[2]))

                            k_r.append(self._format_ce5_key(k.time, safe_r, k.flags))
                            k_g.append(self._format_ce5_key(k.time, safe_g, k.flags))
                            k_b.append(self._format_ce5_key(k.time, safe_b, k.flags))

                        ET.SubElement(var_node, "spline0", keys=",".join(k_r) + ",")
                        ET.SubElement(var_node, "spline1", keys=",".join(k_g) + ",")
                        ET.SubElement(var_node, "spline2", keys=",".join(k_b) + ",")
                    else:
                        k_v = []
                        for k in current_spline.keys:
                            val = k.value
                            if isinstance(val, list):
                                val = val[0]
                            k_v.append(self._format_ce5_key(k.time, val, k.flags))

                        ET.SubElement(var_node, "spline0", keys=",".join(k_v) + ",")
                        # CRITICAL: Empty splines must be present to maintain engine array alignment
                        ET.SubElement(var_node, "spline1", keys="")
                        ET.SubElement(var_node, "spline2", keys="")
                else:
                    # WRITE EMPTY PLACEHOLDERS TO MAINTAIN ORDER
                    ET.SubElement(var_node, "spline0", keys="")
                    ET.SubElement(var_node, "spline1", keys="")
                    ET.SubElement(var_node, "spline2", keys="")

            self._add_constants_block(env_root)

            out_env = input_file.with_suffix(".env")
            out_tod = input_file.parent / f"{input_file.stem}_ce5.xml"

            with open(out_env, "w", encoding="utf-8") as f:
                f.write(self._pretty_print_xml(env_root))

            tod_root = ET.Element(
                "TimeOfDay", {"Time": "12.0", "TimeStart": "0", "TimeEnd": "24", "TimeAnimSpeed": "0"}
            )
            presets = ET.SubElement(tod_root, "Presets")
            ET.SubElement(presets, "Preset", {"Name": f"libs/environmentpresets/{out_env.name}", "Default": "1"})

            with open(out_tod, "w", encoding="utf-8") as f:
                f.write(self._pretty_print_xml(tod_root))

            summary = f"Created:\n- {out_env.name}\n- {out_tod.name}"
            logging.info(f"✅ {summary}")
            return {"summary": summary}

        except Exception as e:
            logging.error(f"Conversion failed: {e}", exc_info=True)
            return {"summary": f"Error: {e}"}
