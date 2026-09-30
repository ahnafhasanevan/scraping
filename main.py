"""Bangladesh University Faculty Scraper - entry point.

Examples:
    python main.py --all                      # every university, photos + CSV
    python main.py --university ewu ulab      # selected universities
    python main.py --all --format xlsx        # Excel instead of CSV
    python main.py --all --no-images          # dataset only
    python main.py --list                     # show university keys
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import config
from external_scrapers import EXTERNAL_SCRIPTS, run_external
from scrapers import SCRAPERS, ScrapeSettings
from utils.cleaner import safe_filename
from utils.exporter import save_records
from utils.http_client import HttpClient
from utils.image_downloader import STATUS_SKIPPED, ImageDownloader

log = logging.getLogger("scraper")


def all_keys() -> list:
    return list(SCRAPERS) + list(EXTERNAL_SCRIPTS)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape faculty photos and details from Bangladeshi university websites.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--all", action="store_true", help="scrape every supported university")
    target.add_argument("--university", "-u", nargs="+", metavar="KEY", help=f"keys: {', '.join(all_keys())}")
    target.add_argument("--list", action="store_true", help="list the supported universities and exit")
    images = parser.add_mutually_exclusive_group()
    images.add_argument("--images", dest="images", action="store_true", default=config.DOWNLOAD_IMAGES,
                        help="download faculty photos")
    images.add_argument("--no-images", dest="images", action="store_false", default=argparse.SUPPRESS,
                        help="skip photos and only build the dataset")
    parser.add_argument("--format", "-f", nargs="+", default=["csv"], choices=["csv", "json", "xlsx", "all"],
                        help="dataset format(s)")
    parser.add_argument("--output", "-o", type=Path, default=config.OUTPUT_DIR, help="output folder")
    parser.add_argument("--delay", type=float, default=config.REQUEST_DELAY, help="seconds between page requests per site")
    parser.add_argument("--max-pages", type=int, default=config.MAX_PAGES_PER_UNIVERSITY, help="page budget per university")
    parser.add_argument("--depth", type=int, default=config.DISCOVERY_DEPTH, help="link depth for finding faculty pages")
    parser.add_argument("--profiles", choices=["auto", "always", "never"], default=config.VISIT_PROFILES,
                        help="visit individual profile pages (auto = only when the list has no photo)")
    parser.add_argument("--render", choices=["auto", "always", "never"], default=_render_default(),
                        help="use a headless browser for JavaScript pages")
    parser.add_argument("--deep", action="store_true", help="also enumerate numbered profile pages (slower)")
    parser.add_argument("--jpg", action="store_true", default=config.CONVERT_TO_JPG, help="convert every photo to JPG")
    parser.add_argument("--include-staff", action="store_true", help="keep officers/lab staff listed with faculty")
    parser.add_argument("--workers", type=int, default=config.DOWNLOAD_WORKERS, help="parallel photo downloads")
    parser.add_argument("--verbose", "-v", action="store_true", help="show debug messages")
    args = parser.parse_args(argv)
    if not (args.all or args.university or args.list):
        parser.print_help()
        print("\nTip: run  python main.py --all  to scrape every university.")
        sys.exit(1)
    return args


def _render_default() -> str:
    value = config.USE_SELENIUM
    if value is True:
        return "always"
    if value is False:
        return "never"
    return str(value)


def prepare_output_dir(requested: Path) -> Path:
    try:
        requested.mkdir(parents=True, exist_ok=True)
        probe = requested / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return requested
    except OSError as exc:
        fallback = config.PROJECT_DIR / "output"
        fallback.mkdir(parents=True, exist_ok=True)
        print(f"WARNING: cannot write to {requested} ({exc}). Using {fallback} instead.")
        return fallback


def setup_logging(log_dir: Path, verbose: bool) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # Windows consoles and non-ASCII names
        except (AttributeError, ValueError):
            pass
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
    file_handler = logging.FileHandler(log_dir / "scraper.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root.addHandler(console)
    root.addHandler(file_handler)
    for noisy in ("urllib3", "selenium", "WDM", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list:
        print("Supported universities:")
        for key, cls in list(SCRAPERS.items()) + list(EXTERNAL_SCRIPTS.items()):
            print(f"  {key:<6} {cls.short_name:<5} {cls.name}  ({cls.homepage})")
        return 0

    keys = all_keys() if args.all else [k.lower() for k in args.university]
    unknown = [k for k in keys if k not in all_keys()]
    if unknown:
        print(f"Unknown university key(s): {', '.join(unknown)}. Valid keys: {', '.join(all_keys())}")
        return 2
    formats = ["csv", "json", "xlsx"] if "all" in args.format else list(dict.fromkeys(args.format))

    output_dir = prepare_output_dir(args.output)
    photos_dir = output_dir / config.IMAGE_DIR_NAME
    data_dir = output_dir / config.DATA_DIR_NAME
    setup_logging(output_dir / config.LOG_DIR_NAME, args.verbose)
    log.info("Output folder: %s", output_dir)

    client = HttpClient(
        user_agent=config.USER_AGENT,
        timeout=config.TIMEOUT,
        max_retries=config.MAX_RETRIES,
        request_delay=args.delay,
        image_delay=config.IMAGE_DELAY,
        respect_robots=config.RESPECT_ROBOTS_TXT,
        allow_insecure_fallback=config.ALLOW_INSECURE_SSL_FALLBACK,
        use_selenium=args.render,
        selenium_wait=config.SELENIUM_PAGE_WAIT,
    )
    settings = ScrapeSettings(
        discovery_depth=args.depth,
        max_pages=args.max_pages,
        max_pagination=config.MAX_PAGINATION_PAGES,
        visit_profiles=args.profiles,
        render=args.render,
        skip_non_academic=config.SKIP_NON_ACADEMIC_STAFF and not args.include_staff,
        deep=args.deep,
    )
    downloader = ImageDownloader(
        client, output_dir, photos_dir, data_dir / "image_manifest.json",
        min_bytes=config.MIN_IMAGE_BYTES, min_side=config.MIN_IMAGE_SIDE, convert_to_jpg=args.jpg,
        workers=args.workers, placeholder_threshold=config.PLACEHOLDER_REPEAT_THRESHOLD,
    )

    all_records = []
    summary = []
    started = time.time()
    try:
        for key in keys:
            if key in EXTERNAL_SCRIPTS:  # stand-alone script, run unchanged
                script = EXTERNAL_SCRIPTS[key]
                if not args.images:
                    log.info("%s: note - this stand-alone script always downloads photos", script.short_name)
                records = run_external(script, photos_dir, output_dir, config.EXTERNAL_SCRIPTS_OWN_OUTPUT)
                save_records(records, data_dir / "raw" / f"{key}_faculty", formats)
                summary.append((script.short_name, len(records), sum(1 for r in records if r.photo_url),
                                sum(1 for r in records if r.photo_file)))
                all_records.extend(records)
                continue
            scraper = SCRAPERS[key](client, settings)
            try:
                records = scraper.run()
            except KeyboardInterrupt:
                raise
            except Exception:
                log.exception("%s: scraper crashed - continuing with the next university", scraper.short_name)
                records = scraper.records
            records.sort(key=lambda r: (r.department.lower(), r.name.lower()))
            if args.images and records:
                folder = f"{scraper.short_name} - {scraper.name}"
                downloader.process(records, safe_filename(folder, 45))
            elif not args.images:
                for record in records:
                    record.photo_status = STATUS_SKIPPED
            written = save_records(records, data_dir / "raw" / f"{key}_faculty", formats)
            saved = sum(1 for r in records if r.photo_file)
            summary.append((scraper.short_name, len(records), sum(1 for r in records if r.photo_url), saved))
            log.info("%s: %d people, %d photos saved -> %s", scraper.short_name, len(records), saved,
                     ", ".join(str(p) for p in written) or "(no dataset written)")
            all_records.extend(records)
    except KeyboardInterrupt:
        log.warning("Interrupted - saving what was collected so far ...")
    finally:
        downloader.save_manifest()
        client.close()

    merged = save_records(all_records, data_dir / "processed" / "all_faculty_merged", formats)
    minutes = (time.time() - started) / 60
    print()
    print(f"{'University':<10}{'Faculty':>9}{'With photo URL':>16}{'Photos saved':>14}")
    print("-" * 49)
    for short, total, with_url, saved in summary:
        print(f"{short:<10}{total:>9}{with_url:>16}{saved:>14}")
    print("-" * 49)
    print(f"{'TOTAL':<10}{sum(s[1] for s in summary):>9}{sum(s[2] for s in summary):>16}{sum(s[3] for s in summary):>14}")
    print(f"\nFinished in {minutes:.1f} min.")
    print(f"Photos : {photos_dir}")
    print(f"Dataset: {', '.join(str(p) for p in merged) or data_dir}")
    print(f"Log    : {output_dir / config.LOG_DIR_NAME / 'scraper.log'}")
    return 0


if __name__ == "__main__":
    if os.name == "nt":
        os.system("")  # enable ANSI colours for tqdm in old Windows consoles
    sys.exit(main())
