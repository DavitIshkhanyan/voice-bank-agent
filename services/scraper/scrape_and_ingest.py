from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
import trafilatura
import yaml
from bs4 import BeautifulSoup
from slugify import slugify

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data/knowledge/raw"
PROCESSED_DIR = ROOT / "data/knowledge/processed"
CONFIG_PATH = Path(__file__).resolve().parent / "config/banks.yaml"

HEADERS = {
    "User-Agent": "voice-bank-agent/1.0 (+educational project scraper)",
}


@dataclass
class Chunk:
    id: str
    bank_id: str
    bank_name: str
    topic: str
    url: str
    title: str
    text: str


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_text(html: str) -> str:
    extracted = trafilatura.extract(html, include_comments=False)
    if extracted:
        return normalize_whitespace(extracted)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.extract()
    return normalize_whitespace(soup.get_text(" "))


def parse_topic_config(topic_value: object) -> dict:
    # Backward-compatible with old list-only format.
    if isinstance(topic_value, list):
        return {
            "seed_urls": topic_value,
            "link_selectors": [],
            "fact_selectors": [],
            "render_js": False,
        }

    if isinstance(topic_value, dict):
        return {
            "seed_urls": topic_value.get("seed_urls", []),
            "link_selectors": topic_value.get("link_selectors", []),
            "fact_selectors": topic_value.get("fact_selectors", []),
            "render_js": bool(topic_value.get("render_js", False)),
        }

    return {
        "seed_urls": [],
        "link_selectors": [],
        "fact_selectors": [],
        "render_js": False,
    }


def extract_short_facts(
    html: str,
    selectors: list[str],
    chunk_size: int = 900,
    chunk_overlap: int = 150,
) -> list[str]:
    if not selectors:
        return []

    soup = BeautifulSoup(html, "html.parser")
    facts: list[str] = []
    seen = set()

    for selector in selectors:
        for node in soup.select(selector):
            fact = normalize_whitespace(node.get_text(strip=True, separator=" "))
            if not fact:
                continue

            candidates = [fact]
            if len(fact) > chunk_size:
                candidates = list(split_chunks(fact, chunk_size=chunk_size, overlap=chunk_overlap))

            for idx, candidate in enumerate(candidates):
                key = candidate.casefold()
                if key in seen:
                    continue
                seen.add(key)
                facts.append(candidate)

            # Allow selectors like `h5 + p` and generic container selectors.
            # if node.name == "p":
            #     heading = node.find_previous_sibling(["h5", "h4", "h3"])
            #     head_text = normalize_whitespace(heading.get_text(" ")) if heading else ""
            #     body_text = normalize_whitespace(node.get_text(" "))
            #     fact = normalize_whitespace(f"{head_text}: {body_text}" if head_text else body_text)
            #     # if len(fact.split()) >= min_words and fact.lower() not in seen:
            #     if fact.lower() not in seen:
            #         seen.add(fact.lower())
            #         facts.append(fact)
            #     continue
            #
            # headings = [normalize_whitespace(h.get_text(" ")) for h in node.select("h5, h4, h3")]
            # values = [normalize_whitespace(p.get_text(" ")) for p in node.select("p, li")]
            # for idx, value in enumerate(values):
            #     if not value:
            #         continue
            #     head_text = headings[idx] if idx < len(headings) else (headings[0] if headings else "")
            #     fact = normalize_whitespace(f"{head_text}: {value}" if head_text else value)
            #     # if len(fact.split()) >= min_words and fact.lower() not in seen:
            #     if fact.lower() not in seen:
            #         seen.add(fact.lower())
            #         facts.append(fact)

    return facts


def split_chunks(text: str, chunk_size: int = 900, overlap: int = 150) -> Iterable[str]:
    if len(text) <= chunk_size:
        yield normalize_whitespace(text)
        return

    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunk = text[start:end]
        if end < len(text):
            last_break = chunk.rfind(" ")
            if last_break > chunk_size // 2:
                chunk = chunk[:last_break]
                end = start + last_break
        chunk = normalize_whitespace(chunk)
        if chunk:
            yield chunk

        # Stop once the final window has been emitted to avoid 1-char tail drift chunks.
        if end >= len(text):
            break

        next_start = end - overlap
        # Guarantee progress even on degenerate content.
        start = next_start if next_start > start else end


def is_low_value_chunk(text: str, *, allow_short: bool = False) -> bool:
    lowered = text.lower()
    words = lowered.split()
    if len(words) < 20 and not allow_short:
        return True

    boilerplate_terms = (
        "subscribe",
        "special offers",
        "utility payments",
        "online insurance",
        "eventhub",
        "myameria",
        "օնլայն բանկինգ",
        "ինտերնետ բանկինգ",
    )
    if sum(1 for term in boilerplate_terms if term in lowered) >= 2:
        return True

    unique_ratio = len(set(words)) / max(1, len(words))
    return unique_ratio < 0.30


def same_domain(base_url: str, candidate: str) -> bool:
    return urlparse(base_url).netloc.replace("www.", "") == urlparse(candidate).netloc.replace("www.", "")


def fetch(url: str, timeout: int = 20) -> requests.Response | None:
    try:
        resp = requests.get(url, timeout=timeout, headers=HEADERS)
        if resp.status_code >= 400:
            return None
        return resp
    except requests.RequestException:
        return None


def fetch_rendered_html(url: str, timeout_seconds: int = 30) -> str | None:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def fetch_html(url: str, timeout: int = 20, render_js: bool = False) -> str | None:
    if render_js:
        rendered = fetch_rendered_html(url, timeout_seconds=max(timeout, 30))
        if rendered:
            return rendered

    resp = fetch(url, timeout=timeout)
    if resp is None:
        return None
    return resp.text


def pick_links(html: str, base_url: str, selectors: list[str] | None = None) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []

    if selectors:
        for selector in selectors:
            for node in soup.select(selector):
                if node.name == "a" and node.get("href"):
                    href = urljoin(base_url, node["href"])
                    if href.startswith("http"):
                        out.append(href.split("#")[0])
                    continue

                for a_tag in node.select("a[href]"):
                    href = urljoin(base_url, a_tag["href"])
                    if href.startswith("http"):
                        out.append(href.split("#")[0])

    # Generic fallback to catch missed links across unknown templates.
    # for a_tag in soup.find_all("a", href=True):
    #     href = urljoin(page_url, a_tag["href"])
    #     if not href.startswith("http"):
    #         continue
    #     out.append(href.split("#")[0])
    # Preserve order, dedupe.
    seen = set()
    deduped = []
    for link in out:
        if link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped


def scrape() -> list[Chunk]:
    conf = load_config()
    all_chunks: list[Chunk] = []

    for bank in conf["banks"]:
        bank_id = bank["id"]
        bank_name = bank["name"]
        base_url = bank["base_url"]

        for topic, topic_value in bank["topics"].items():
            topic_conf = parse_topic_config(topic_value)
            seed_urls = topic_conf["seed_urls"]
            link_selectors = topic_conf["link_selectors"]
            fact_selectors = topic_conf["fact_selectors"]
            render_js = topic_conf["render_js"]

            visit_queue = list(seed_urls)
            seen_urls = set()

            while visit_queue:
                url = visit_queue.pop(0)
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                html = fetch_html(url, render_js=render_js)
                if html is None:
                    continue

                soup = BeautifulSoup(html, "html.parser")
                title = normalize_whitespace(soup.title.get_text(" ", strip=True)) if soup.title else url

                raw_name = f"{bank_id}-{topic}-{slugify(url)[:90]}.html"
                (RAW_DIR / raw_name).write_text(html, encoding="utf-8")

                seen_piece_hashes: set[str] = set()

                for fact_idx, fact_text in enumerate(extract_short_facts(html, fact_selectors)):
                    fact_hash = hashlib.sha1(fact_text.lower().encode("utf-8")).hexdigest()
                    if fact_hash in seen_piece_hashes:
                        continue
                    seen_piece_hashes.add(fact_hash)

                    chunk_id = f"{bank_id}:{topic}:{slugify(url)[:50]}:fact:{fact_idx}"
                    all_chunks.append(
                        Chunk(
                            id=chunk_id,
                            bank_id=bank_id,
                            bank_name=bank_name,
                            topic=topic,
                            url=url,
                            title=title,
                            text=fact_text,
                        )
                    )

                for link in pick_links(html, base_url=base_url, selectors=link_selectors):
                    if not same_domain(base_url, link):
                        continue
                    if link not in seen_urls:
                        visit_queue.append(link)

                time.sleep(0.3)

    return all_chunks


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    chunks = scrape()
    out_path = PROCESSED_DIR / "chunks.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")

    print(f"Wrote {len(chunks)} chunks to {out_path}")


if __name__ == "__main__":
    main()

