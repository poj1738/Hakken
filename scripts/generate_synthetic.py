#!/usr/bin/env python3
"""Generate the MedTrace synthetic world. Seeded, reproducible, no real data.

Implements `docs/DATA_SPEC.md`. Produces four heterogeneous patient silos, the
ground truth they were generated from, and the Zetaris-envelope fixtures that
`SAMPLE_MODE` replays.

**Nothing here is real.** Every patient, name, identifier, medication statement
and discrepancy is synthesised from a seed. `ihi_syn` is `SYN-` plus 12 digits,
which is deliberately not the 16-digit IHI format and never carries the real
`800360` prefix. There are no Medicare numbers and no prescriber numbers.

Two documented deviations from `docs/DATA_SPEC.md`:

1. **Population is 200 (100 tune / 100 held-out), as specified** -- restored
   25 Oct. It was 40 from 24 Oct, which left several finding types with 1-4
   instances per split and hid the largest error source entirely (21 of 32
   false positives appeared only at 200). Silos are ~6 MB; Zetaris latency
   tracks bytes scanned, so re-time the live queries after `make refresh`.
2. **`random.Random` rather than `numpy.random.Generator(PCG64(...))`.** The
   spec names numpy; using it would add a dependency to `requirements.txt`, a
   shared file, for the RNG alone. Determinism is what actually matters and is
   asserted by a test: every patient gets its own stream derived from the master
   seed, which is what `SeedSequence.spawn` is for. Flagged for Arpon.

Outputs:

  data/synthetic/silos/{emr,gp,pharmacy,patient}.json   {"records": [...]}
  data/synthetic/ground_truth.json                      never served to agents
  tests/fixtures/medtrace/Q1__P00xx.json                Zetaris envelopes
  tests/fixtures/medtrace/Q2__P00xx.json
  tests/fixtures/medtrace/Q3__P00xx.json

Usage:
    python3 scripts/generate_synthetic.py
    python3 scripts/generate_synthetic.py --patients 200 --fixtures 10
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import pathlib
import random
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.domain.packs.medtrace.queries import HARMONISED_COLUMNS, IDENTITY_COLUMNS

SEED = 20261024
GENERATOR_VERSION = "1.0.0"
AS_OF = dt.date(2026, 10, 24)

SRC = pathlib.Path("data/reference_src")
OUT = pathlib.Path("data/synthetic")
FIXTURES = pathlib.Path("tests/fixtures/medtrace")

#: Prefixed to both of the above by `--out-root`. The determinism test runs the
#: generator twice and compares the runs; without somewhere else to write, it
#: overwrote `data/synthetic/` and the committed fixtures every time the suite
#: ran. On a fresh clone that is worse than untidy: `data/reference/lexicon.json`
#: is gitignored, so CI regenerated the silos *without* the real codes, replaced
#: the committed fixtures with them, and then asserted against data nobody had
#: committed. Tests must read the artefacts we ship, not ones they just made.
OUT_ROOT = pathlib.Path(".")

SOURCES = ("emr", "gp", "pharmacy", "patient")

# DATA_SPEC 3: age bands and sex
AGE_BANDS = (((60, 69), 0.25), ((70, 79), 0.38), ((80, 90), 0.37))
P_FEMALE = 0.53
# DATA_SPEC 3: regular medicines per patient
MED_COUNTS = ((5, 0.12), (6, 0.13), (7, 0.14), (8, 0.14), (9, 0.13), (10, 0.12), (11, 0.11), (12, 0.11))

# DATA_SPEC 7: identity corruption rates, per source
MISSING_IHI = {"emr": 0.05, "gp": 0.20, "pharmacy": 0.30, "patient": 0.70}
NICKNAME_RATE = {"gp": 0.15, "patient": 0.25, "pharmacy": 0.03, "emr": 0.01}
TYPO_NAME_RATE = {"patient": 0.08, "gp": 0.03, "pharmacy": 0.03, "emr": 0.01}
DOB_SWAP_RATE = {"patient": 0.04, "gp": 0.01, "pharmacy": 0.01, "emr": 0.0}
MAIDEN_RATE_FEMALE = 0.08
ADDRESS_MOVE_RATE = 0.10

# DATA_SPEC 6: coverage
NO_GP_RATE = 0.08
NO_PATIENT_RATE = 0.05
NO_PHARMACY_RATE = 0.03
SECOND_PHARMACY_RATE = 0.10
PRIVATE_SCRIPT_RATE = 0.04
PRIOR_DISCHARGE_RATE = 0.35
PATIENT_ONLY_RATE = 0.66
STALE_GP_DOC_RATE = 0.15

# DATA_SPEC 9: timeline
CEASED_MEAN = 1.5
GP_RETAIN_CEASED_ACTIVE = 0.30
POSSIBLY_CEASED_GRACE_DAYS = 90

# DATA_SPEC 8: hidden per-source per-attribute error rates (the H-MEM target)
HIDDEN_ERROR_RATES: dict[str, dict[str, float]] = {
    "emr": {"existence_omission": 0.055, "existence_commission": 0.024, "dose": 0.030,
            "frequency": 0.020, "identity": 0.01},
    "gp": {"existence_noncurrent": 0.12, "existence_omission": 0.08, "dose": 0.08,
           "frequency": 0.06, "name": 0.18, "dob": 0.02},
    "pharmacy": {"existence_omission": 0.14, "existence_commission": 0.06, "dose": 0.12,
                 "strength_form": 0.01, "name": 0.05, "dob": 0.01},
    "patient": {"existence_omission": 0.15, "existence_complementary": 0.02, "dose": 0.18,
                "frequency": 0.12, "med_name": 0.25, "dob": 0.06, "still_taking": 0.08},
}

SURNAMES = ["Smith", "Nguyen", "O'Brien", "Williams", "Brown", "Patel", "Chen", "Taylor",
            "Wilson", "Kaur", "D'Souza", "Jones", "Martin", "Lee", "Harris", "Walker",
            "Young", "Hall", "Wright", "Clarke", "Papadopoulos", "Rossi", "Murphy", "Singh"]
LAY_TERMS = {
    "warfarin": "my blood thinner", "apixaban": "my blood thinner",
    "rivaroxaban": "my blood thinner", "furosemide": "the water tablet",
    "salbutamol": "my blue puffer", "atorvastatin": "cholesterol tablet",
    "rosuvastatin": "cholesterol tablet", "levothyroxine": "thyroid tablet",
    "pantoprazole": "reflux tablet", "allopurinol": "gout tablet",
    "metformin": "sugar tablet", "insulin glargine": "my insulin",
    "glyceryl trinitrate": "spray under the tongue", "temazepam": "sleeping tablet",
    "paracetamol": "arthritis Panadol", "tamsulosin": "prostate tablet",
}
#: DATA_SPEC 9.5: regimens whose dose changes by phone, with no new script, so
#: the dispensing record cannot reconstruct it.
PHONE_DOSE_GENERICS = ("warfarin", "insulin glargine", "prednisolone")


def phone_dose_gp_directions(med: "Med", rng: random.Random, usual: str) -> str:
    """What the GP list says once the dose has moved by phone (DATA_SPEC 9.5).

    Warfarin: half "as directed per INR", half the stale fixed dose. Insulin: "as
    directed" 60% of the time. Prednisolone: the stale dose -- the GP list is
    where the original prescription lives, not the taper step.
    """
    if med.generic == "warfarin":
        return "as directed per INR" if rng.random() < 0.5 else usual
    if med.generic == "insulin glargine":
        return "as directed" if rng.random() < 0.6 else usual
    return usual


def phone_dose_patient_words(med: "Med", rng: random.Random) -> str:
    """What the patient says about a dose that moved by phone (DATA_SPEC 9.5).

    Warfarin: 60% describe the current alternating regimen, 40% are unsure.
    Insulin titration and the current prednisolone step exist **only** here,
    which is exactly why no structured source can confirm them.
    """
    mg = strength_mg(med.strength) or 0.0
    if med.generic == "warfarin":
        if rng.random() < 0.6 and mg > 1:
            return f"{mg - 1:g} mg Mon Wed Fri, {mg:g} mg the other days"
        return "not sure how much now, the clinic changes it"
    if med.generic == "insulin glargine":
        return rng.choice(["up 2 units every three days", "they told me to go up a bit",
                           "changes with my sugars"])
    return rng.choice(["down to the next step this week", "cutting down each week",
                       "on the lower dose now"])


FREQ_WORDS = {"1 mane": "one in the morning", "1 nocte": "one at night",
              "1 daily": "one a day", "1 bd": "morning and night", "2 tds": "two three times a day",
              "1 tds": "one three times a day", "prn": "only when I need it"}


def log(msg: str) -> None:
    print(msg, flush=True)


def read_csv(path: pathlib.Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


def pick(rng: random.Random, weighted: tuple) -> object:
    total = sum(w for _, w in weighted)
    r = rng.random() * total
    upto = 0.0
    for value, weight in weighted:
        upto += weight
        if r <= upto:
            return value
    return weighted[-1][0]


def iso(d: dt.date | None) -> str:
    return d.isoformat() if d else ""


def ddmmyyyy(d: dt.date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def swap_day_month(d: dt.date) -> dt.date | None:
    if d.day > 12 or d.day == d.month:
        return None
    try:
        return dt.date(d.year, d.day, d.month)
    except ValueError:
        return None


def poisson(rng: random.Random, mean: float) -> int:
    """Knuth's method. `int(expovariate(1/mean))` floors to 0 far too often, which
    would leave most patients with no ceased medicines and so no `stale_listing`
    or `commission` to plant."""
    import math

    limit, k, product = math.exp(-mean), 0, 1.0
    while True:
        product *= rng.random()
        if product <= limit:
            return k
        k += 1


def typo(rng: random.Random, text: str) -> str:
    """One-character corruption that is guaranteed to change the string.

    The doubling branch could return the input unchanged ("Tom" -> "Tom"), so
    the ground truth recorded a corruption that was not there and the linker
    was credited with surviving a typo it never saw.
    """
    if len(text) < 4:
        return text
    for _ in range(6):
        i = rng.randrange(1, len(text) - 1)
        out = (text[:i] + text[i + 1:]) if rng.random() < 0.5 else (text[:i] + text[i] + text[i:])
        if out != text:
            return out
    return text[:-1]


# --------------------------------------------------------------------------- #
# Medicine selection (DATA_SPEC 4.1)
# --------------------------------------------------------------------------- #

#: DATA_SPEC 4.2 exclusion rules. At most one agent from each of these groups,
#: because two anticoagulants or two RAS blockers is a prescribing error, not a
#: realistic list -- and planting one by accident would create a `duplication`
#: finding that the ground truth does not know about, scoring as a false positive.
ANTICOAGULANT_PREFIXES = ("B01AA", "B01AE", "B01AF")
RAS_PREFIXES = ("C09A", "C09B", "C09C", "C09D")


class Product(dict):
    """One row of `data/reference_src/medicines.csv`, with typed accessors."""

    @property
    def ingredients(self) -> list[str]:
        return [i for i in self["ingredients"].split(";") if i]

    @property
    def brands(self) -> list[str]:
        return [b for b in self["brands"].split(";") if b] or [""]

    @property
    def strengths(self) -> list[str]:
        return [s for s in self["strengths"].split(";") if s] or [""]

    @property
    def is_addon(self) -> bool:
        return self["is_addon"] == "1"

    def override_for(self, column: str, strength: str) -> int:
        """A per-strength override from `column`, or 0 if none.

        The column is either one value for every strength, or a ";"-separated
        list aligned with `strengths` -- the same convention as brands and
        strengths. One value per product gave every prednisolone strength the
        200-tablet pack that is right only for 5 mg, which made a finished
        25 mg course look like 200 days of supply.
        """
        raw = (self.get(column) or "").strip()
        if not raw:
            return 0
        values = raw.split(";")
        if len(values) > 1:
            try:
                raw = values[self.strengths.index(strength)]
            except (ValueError, IndexError):
                return 0
        try:
            return int(raw or 0)
        except ValueError:
            return 0


def doses_per_day(regimen: str) -> float:
    """Doses per day from a regimen string. Weekly agents divide by 7."""
    r = regimen.lower()
    n = 2.0 if r.startswith("2 ") else 1.0
    if "6-monthly" in r:
        return n / 182.0
    if "yearly" in r:
        return n / 365.0
    if "monthly" in r:
        return n / 30.0
    if "weekly" in r:
        return n / 7.0
    if "qid" in r:
        return n * 4
    if "tds" in r:
        return n * 3
    if " bd" in r or r.endswith("bd"):
        return n * 2
    if "1 to 2" in r:
        return 1.5
    return n


def strength_mg(strength: str) -> float | None:
    """Leading number in mg. `microgram` is scaled -- a mcg/mg confusion is a
    1000x error that lands on digoxin and levothyroxine, both high-risk."""
    import re

    m = re.match(r"\s*([\d.]+)", strength or "")
    if not m:
        return None
    value = float(m.group(1))
    low = (strength or "").lower()
    if "microgram" in low:
        return value / 1000.0
    if "iu" in low or "unit" in low:
        return value
    return value


def choose_medicines(rng: random.Random, bundles: dict[str, list[Product]], sex: str,
                     target: int) -> list[Product]:
    chosen: list[Product] = []
    anticoagulant = False
    ras = False

    weight_key = "weight_f" if sex == "F" else "weight_m"
    order = sorted(bundles, key=lambda b: -float(bundles[b][0][weight_key]))
    used: set[str] = set()

    def take(bundle_id: str) -> None:
        nonlocal anticoagulant, ras
        rows = bundles[bundle_id]
        anchors = [r for r in rows if not r.is_addon
                   and (not r["sex_restrict"] or r["sex_restrict"] == sex)]
        if not anchors:
            return
        used.add(bundle_id)
        anchor = pick(rng, tuple((r, float(r["share"])) for r in anchors))
        assert isinstance(anchor, Product)
        candidates = [anchor] + [r for r in rows if r.is_addon and rng.random() < float(r["share"])]
        for product in candidates:
            atc = product["atc"]
            if any(atc.startswith(pre) for pre in ANTICOAGULANT_PREFIXES):
                if anticoagulant:
                    continue
                anticoagulant = True
            if any(atc.startswith(pre) for pre in RAS_PREFIXES):
                if ras:
                    continue
                ras = True
            # Exclusions must be checked on the INGREDIENT, not the product.
            # Checking the product let Coversyl Plus (perindopril/indapamide)
            # and Coveram (perindopril/amlodipine) both be drawn, giving one
            # patient two perindopril sources and two amlodipine sources on the
            # admission chart -- a real, harmful duplication that the ground
            # truth did not know about, so the tool would be penalised for
            # correctly finding it. Found by a clinical review of the output.
            taken = {i for c in chosen for i in c.ingredients}
            if set(product.ingredients) & taken:
                continue
            chosen.append(product)

    # Pass 1: include each bundle with probability = its (sex-specific) weight.
    for bundle_id in order:
        weight = float(bundles[bundle_id][0][weight_key])
        if weight > 0 and rng.random() <= weight:
            take(bundle_id)

    # Pass 2 (DATA_SPEC 4.1 steps 2 and 4): "resample if fewer than 2" bundles,
    # and "add bundles by descending weight" until the drawn medicine count is
    # met. Without this the population lands at ~4.3 medicines per patient
    # against the spec's 5 to 12 (mean 8.4), and every per-medicine planting
    # rate is then applied to too small a denominator.
    for bundle_id in order:
        if len(chosen) >= target and len(used) >= 2:
            break
        if bundle_id not in used and float(bundles[bundle_id][0][weight_key]) > 0:
            take(bundle_id)

    # DATA_SPEC 4.1 step 4: never trim anticoagulants, insulin or levothyroxine.
    protected = ("B01A", "A10A", "H03AA")
    if len(chosen) > target:
        keep = [c for c in chosen if any(c["atc"].startswith(p) for p in protected)]
        rest = [c for c in chosen if c not in keep]
        chosen = keep + rest[: max(0, target - len(keep))]
    return chosen


# --------------------------------------------------------------------------- #
# Patients
# --------------------------------------------------------------------------- #


#: Australian PI maximum maintenance dose for people over 65, in mg/day.
#: Escitalopram 20 mg at 71 is above the PI and a pharmacist queries it on
#: sight, so it is capped rather than generated as an accidental error.
#: Citalopram carries a parallel TGA limit if it is ever added.
ELDERLY_MAX_MG: dict[str, float] = {"escitalopram": 10.0}
ELDERLY_FROM_AGE = 65


class Med:
    """One medicine in a patient's truth, with its timeline and dispensing."""

    def __init__(self, product: Product, rng: random.Random, age: int | None = None) -> None:
        self.product = product
        self.generic = product["generic"]
        self.brand = rng.choice(product.brands)
        self.strength = rng.choice(product.strengths)
        cap = ELDERLY_MAX_MG.get(self.generic)
        if cap is not None and age is not None and age >= ELDERLY_FROM_AGE:
            allowed = [s for s in product.strengths
                       if (strength_mg(s) or 0) <= cap] or product.strengths[:1]
            self.strength = rng.choice(allowed)
        self.regimen = product["regimen"]
        self.release = product["release"]
        self.route = product["route"]
        self.atc = product["atc"]
        self.high_risk = product["high_risk"]
        self.ingredients = product.ingredients
        self.form = product["form"]
        self.is_otc = product["bundle_id"] == "18"
        self.start = AS_OF - dt.timedelta(days=rng.randint(60, 3650))
        self.stop: dt.date | None = None
        self.changed_by_phone = False
        self.private = rng.random() < PRIVATE_SCRIPT_RATE
        self.hidden_at_second_pharmacy = False
        self.dispensings: list[dt.date] = []
        per_day = doses_per_day(self.regimen)
        mg = strength_mg(self.strength)
        self.true_daily_dose_mg = round(mg * per_day, 4) if mg is not None else None
        # Real PBS maximum quantity where the lexicon has one; a hand override
        # in medicines.csv beats it; the 60/30 guess is the last resort and
        # only applies to items with no PBS listing (OTC, and the few
        # private-script products).
        real_qty, real_repeats = PACKS.get((self.generic, self.brand, self.strength), (0, 0))
        override_repeats = product.override_for("repeats_override", self.strength)
        self.pbs_repeats = override_repeats or real_repeats
        self.pack_qty = (product.override_for("pack_qty_override", self.strength) or real_qty
                         or (60 if per_day >= 2 else 30))
        # A device pack is ONE unit that lasts about a month, so dividing it by
        # doses-per-day collapsed days_supply to the 7-day floor and let an
        # inhaler or insulin pen be dispensed 50+ times a year. Pack size says
        # nothing about duration for a device -- the same reason normalise.py
        # refuses to infer a daily dose from one.
        self.is_device = any(w in (product["form"] + " " + product["route"]).lower()
                             for w in ("inhaler", "spray", "patch", "injection", "pen"))
        if self.is_device:
            self.days_supply = 30
        else:
            # Pack arithmetic alone is not trustworthy here: PBS records
            # pack_size as 1 for some items (the quantity unit is a pack, not a
            # tablet -- Rosuzet is listed as 1), which made one patient's
            # Rosuzet look like a 7-day supply and gave them 53 fills in a
            # year. A repeat count is the honest chronic/acute signal, and it
            # comes from the same real PBS row: an item with repeats is ongoing
            # therapy, dispensed about monthly in Australia, so a month is the
            # floor. An item with none is a one-off course and keeps whatever
            # the pack holds.
            pack_days = int(self.pack_qty / per_day) if per_day > 0 else 30
            floor = 28 if self.pbs_repeats > 0 else 5
            self.days_supply = max(floor, pack_days)
        self.gp_listing = "active"
        regimen = self.regimen.lower()
        self.prn_like = ("prn" in regimen or "as needed" in regimen
                         or "when" in regimen)

    @property
    def current(self) -> bool:
        return self.stop is None

    def cease(self, rng: random.Random) -> None:
        self.stop = AS_OF - dt.timedelta(days=rng.randint(30, 365))
        # DATA_SPEC 9.1: a ceased medicine often stays on the GP list.
        roll = rng.random()
        self.gp_listing = ("active" if roll < GP_RETAIN_CEASED_ACTIVE
                           else "ceased" if roll < 0.90 else "deleted")

    def build_dispensings(self, rng: random.Random) -> None:
        """Fills over the 12-month lookback, spaced by adherence plus jitter.

        Three limits, all added after a clinical review found the dispensing
        layer was the least believable part of the data:

        * **PRN items get 0-2 fills a year.** A GTN spray came out with 21 fills,
          about 4,200 doses, for a medicine taken only during angina. PBS item
          8171C is one 200-actuation canister with 5 repeats.
        * **A hard ceiling of `365 / days_supply` fills**, where days_supply
          comes from the item's real PBS maximum quantity rather than a guessed
          pack. Paracetamol 665 mg MR came out with 29 fills, then 37 once the
          ceiling was added against a guessed pack of 60. More fills than the
          dose can consume is oversupply, which no pharmacy record would show.
          A device is exempt from the division: an inhaler's pack of 1 says
          nothing about how long it lasts, so it is treated as a month.
        * **Nothing dispensed on or after the admission date.** Two of three
          sample patients had a fill dated the day of admission.
        """
        if self.is_otc or self.route == "IV":
            return
        pdc = min(1.0, max(0.3, rng.betavariate(6, 1.5)))
        self.pdc = pdc
        end = min(self.stop or AS_OF, AS_OF - dt.timedelta(days=1))
        day = max(self.start, AS_OF - dt.timedelta(days=365))

        if self.prn_like:
            # A PRN medicine is dispensed when the pack runs out, which for an
            # as-needed item is rarely and irregularly.
            for _ in range(rng.randint(0, 2)):
                if day <= end:
                    self.dispensings.append(day)
                    day += dt.timedelta(days=rng.randint(120, 300))
            return

        # Most fills the supply could actually be exhausted in a year, plus one
        # for a part-used pack at the start of the window. Derived from
        # days_supply rather than pack size, so it is correct for devices too.
        ceiling = max(1, int(365 / max(self.days_supply, 1)) + 1)
        while day <= end and len(self.dispensings) < ceiling:
            self.dispensings.append(day)
            gap = self.days_supply / pdc + rng.gauss(0, 3)
            day = day + dt.timedelta(days=max(int(0.6 * self.days_supply), int(gap)))

    def possibly_ceased(self) -> bool:
        """DATA_SPEC 9.4, with its suppressions."""
        if not self.dispensings or self.private or self.hidden_at_second_pharmacy:
            return False
        if any(w in self.regimen.lower() for w in ("prn", "6-monthly", "yearly")):
            return False
        runout = self.dispensings[-1] + dt.timedelta(days=self.days_supply)
        return (AS_OF - runout).days > POSSIBLY_CEASED_GRACE_DAYS


class Patient:
    def __init__(self, index: int, rng: random.Random, bundles: dict[str, list[Product]],
                 nicknames: dict[str, tuple[list[str], str]]) -> None:
        self.key = f"P{index:04d}"
        self.rng = rng
        band = pick(rng, AGE_BANDS)
        assert isinstance(band, tuple)
        self.age = rng.randint(*band)
        self.sex = "F" if rng.random() < P_FEMALE else "M"
        self.dob = AS_OF - dt.timedelta(days=self.age * 365 + rng.randint(0, 364))
        self.family_name = rng.choice(SURNAMES)
        self.previous_surname = ""
        if self.sex == "F" and rng.random() < MAIDEN_RATE_FEMALE:
            self.previous_surname = rng.choice([s for s in SURNAMES if s != self.family_name])
        # The given name must match the drawn sex. Without this, 35% of patients
        # got a contradicting name ("Kenneth Lee, F"), which a pharmacist spots
        # instantly -- and `sex` is a real identity comparator, so a scrambled
        # name/sex pairing also makes linkage look easier than it is.
        pool = sorted(n for n, (_v, sex) in nicknames.items() if sex == self.sex)
        self.given_name = rng.choice(pool) if pool else ("Alex" if self.sex == "M" else "Robin")
        self.nicknames = nicknames.get(self.given_name, ([], self.sex))[0]
        self.postcode = f"{rng.randint(2000, 2999)}"
        self.old_postcode = f"{rng.randint(3000, 3999)}" if rng.random() < ADDRESS_MOVE_RATE else ""
        self.ihi = f"SYN-{rng.randrange(10**11, 10**12):012d}"

        self.ids = {
            "emr": f"MRN{index:07d}",
            "gp": f"GPP{index:06d}",
            "pharmacy": f"C{index:06d}",
            "patient": f"INT{index:05d}",
        }
        self.pharmacy_id = f"PHX{rng.randint(1, 12):02d}"
        self.present = {
            "emr": True,
            "gp": rng.random() > NO_GP_RATE,
            "pharmacy": rng.random() > NO_PHARMACY_RATE,
            "patient": rng.random() > NO_PATIENT_RATE,
        }
        self.second_pharmacy = rng.random() < SECOND_PHARMACY_RATE
        self.prior_discharge = rng.random() < PRIOR_DISCHARGE_RATE
        self.gp_doc_stale = rng.random() < STALE_GP_DOC_RATE

        target = pick(rng, MED_COUNTS)
        assert isinstance(target, int)
        self.meds: list[Med] = [Med(p, rng, self.age)
                                for p in choose_medicines(rng, bundles, self.sex, target)]
        self.otc: list[Med] = []
        self.overlay_from: Patient | None = None

    def induce_duplication(self, rng: random.Random, products: list[Product]) -> None:
        """Deliberately create an ingredient overlap, at DATA_SPEC 5.2's rate.

        Left to chance this fires only when bundle sampling happens to draw a
        combination alongside one of its own components, which is uncontrolled:
        in a 40-patient run it produced three instances and all three landed in
        held-out, so `duplication` had nothing to tune against. The spec plants
        it at 0.18 per patient, so it is induced -- "GP lists Caduet and
        Lipitor" is the archetype.
        """
        if rng.random() >= 0.18:
            return
        mine = {m.generic for m in self.meds}
        # Prefer a combination whose component this patient already takes.
        combos = [p for p in products if len(p.ingredients) > 1
                  and p["generic"] not in mine
                  and set(p.ingredients) & {g for m in self.meds for g in m.ingredients}]
        if not combos:
            # Otherwise add a combination, then one of its components.
            combos = [p for p in products if len(p.ingredients) > 1 and p["generic"] not in mine]
            if not combos:
                return
            combo = rng.choice(combos)
            component = next((p for p in products if len(p.ingredients) == 1
                              and p["generic"] in combo.ingredients
                              and p["generic"] not in mine), None)
            if component is None:
                return
            self.meds.extend([Med(combo, rng), Med(component, rng)])
            return
        self.meds.append(Med(rng.choice(combos), rng))

    def finalise(self, rng: random.Random) -> None:
        for med in self.meds:
            med.build_dispensings(rng)
            if self.second_pharmacy and rng.random() < 0.4:
                med.hidden_at_second_pharmacy = True


# --------------------------------------------------------------------------- #
# Silo rendering (DATA_SPEC 2.1 to 2.4) -- deliberately heterogeneous
# --------------------------------------------------------------------------- #


class Rows:
    """Row accumulators with per-source `row_id` counters."""

    def __init__(self) -> None:
        self.data: dict[str, list[dict[str, str]]] = {s: [] for s in SOURCES}
        self.counters: collections.Counter = collections.Counter()
        self.prefix = {"emr": "EMR", "gp": "GP", "pharmacy": "PHM", "patient": "PAT"}

    def new_id(self, source: str) -> str:
        self.counters[source] += 1
        return f"{self.prefix[source]}-{self.counters[source]:06d}"

    def add(self, source: str, row: dict[str, str]) -> str:
        row_id = self.new_id(source)
        row["row_id"] = row_id
        self.data[source].append({k: ("" if v is None else str(v)) for k, v in row.items()})
        return row_id


def render_name_for(source: str, p: Patient, rng: random.Random,
                    corruptions: list[dict[str, object]]) -> tuple[str, str, str]:
    """Given name, family name and the DOB text one source would hold."""
    given = p.given_name
    family = p.family_name
    if p.nicknames and rng.random() < NICKNAME_RATE.get(source, 0.0):
        given = rng.choice(p.nicknames)
        corruptions.append({"operator": "nickname", "source": source, "field": "given",
                            "before": p.given_name, "after": given})
    if rng.random() < TYPO_NAME_RATE.get(source, 0.0):
        before = given
        given = typo(rng, given)
        corruptions.append({"operator": "single_char_typo", "source": source, "field": "given",
                            "before": before, "after": given})
    if p.previous_surname and source != "emr" and rng.random() < 0.5:
        family = p.previous_surname
        corruptions.append({"operator": "maiden_married_surname", "source": source,
                            "field": "family", "before": p.family_name, "after": family})
    dob = p.dob
    if rng.random() < DOB_SWAP_RATE.get(source, 0.0):
        swapped = swap_day_month(p.dob)
        if swapped:
            dob = swapped
            corruptions.append({"operator": "dob_day_month_swap", "source": source,
                                "field": "dob", "before": iso(p.dob), "after": iso(swapped)})
    return given, family, iso(dob)


def ihi_for(source: str, p: Patient, rng: random.Random) -> str:
    return "" if rng.random() < MISSING_IHI[source] else p.ihi


def postcode_for(source: str, p: Patient, rng: random.Random) -> str:
    if p.old_postcode and source != "emr" and rng.random() < 0.5:
        return p.old_postcode
    return p.postcode


def render(p: Patient, rows: Rows, codes: dict[tuple[str, str, str], dict[str, str]],
           rng: random.Random) -> tuple[list[dict[str, object]], list[dict[str, object]],
                                        list[dict[str, object]]]:
    """Write one patient into the four silos. Returns (planted, notices, corruptions)."""
    planted: list[dict[str, object]] = []
    notices: list[dict[str, object]] = []
    corruptions: list[dict[str, object]] = []
    overlay_ids: list[str] = []
    pid = p.key

    def code_for(med: Med, kind: str) -> str:
        entry = codes.get((med.generic, med.brand, med.strength), {})
        return entry.get(kind, "")

    def plant(kind: str, med: Med, sources: list[str], row_ids: list[str],
              detail: dict[str, object], intent: str) -> None:
        planted.append({
            "id": f"F{pid[1:]}-{len(planted) + 1:02d}", "type": kind, "generic": med.generic,
            "sources_involved": sources, "row_ids": row_ids, "detail": detail,
            "high_risk_class": med.high_risk or None, "intent": intent,
        })

    # -- dose_unconfirmable (DATA_SPEC 9.5) ---------------------------------
    # Decided BEFORE any silo is written, because the mechanism has to show up
    # in the GP and patient rows. It used to be decided after rendering and
    # changed nothing, so the ground truth said "dose changed by phone" while
    # every source agreed on the old dose: a finding with no visible reason.
    for med in p.meds:
        if med.generic in PHONE_DOSE_GENERICS and med.current:
            if rng.random() < 0.85:
                med.changed_by_phone = True
                plant("dose_unconfirmable", med, ["gp", "pharmacy", "patient"], [],
                      {"mechanism": "dose changed without a new script"},
                      "possibly_intentional" if rng.random() < 0.6 else "likely_unintentional")

    # -- EMR ----------------------------------------------------------------
    given, family, dob_text = render_name_for("emr", p, rng, corruptions)
    emr_base = {"mrn": p.ids["emr"], "ihi_syn": ihi_for("emr", p, rng), "given_name": given,
                "family_name": family, "dob": dob_text, "sex": p.sex,
                "postcode": postcode_for("emr", p, rng)}
    charted: dict[str, str] = {}
    for med in p.meds:
        if not med.current:
            continue
        # omission (DATA_SPEC 5.2): supported pre-admission, absent from the chart
        if rng.random() < HIDDEN_ERROR_RATES["emr"]["existence_omission"] * 1.5:
            # Row ids left empty on purpose: resolve_row_ids fills them once this
            # patient's GP and pharmacy rows exist. This used to scan
            # rows.data["gp"] here -- but the EMR is rendered first, so at this
            # point that list held only EARLIER patients' rows. Any brand match
            # was another person's record, and because resolve_row_ids skips a
            # finding that already has ids, 9 of 20 omissions ended up citing
            # someone else's rows and could never be matched by row overlap.
            plant("omission", med, ["gp", "pharmacy"], [],
                  {"reason": "not charted at admission"},
                  "documented_intentional" if rng.random() < 0.30 else "likely_unintentional")
            continue
        dose = strength_mg(med.strength)
        note = ""
        intent_doc = False
        if rng.random() < 0.08:
            # "withheld: contrast" applies to metformin (and nephrotoxics), not
            # to a beta blocker or a calcium channel blocker: RANZCR advises
            # continuing metformin above eGFR 30, and NSW TAG states metformin
            # is not nephrotoxic. The generator was annotating any medicine with
            # it, which a pharmacist spots immediately.
            if med.generic == "metformin":
                note = rng.choice(["withheld: contrast", "withheld: AKI"])
            elif med.atc.startswith(("C09", "C03")):
                note = "withheld: AKI"
            elif med.atc.startswith("C07"):
                note = rng.choice(["withheld: bradycardia", "withheld: hypotension"])
            else:
                note = rng.choice(["withheld: nil by mouth", "withheld: hypotension"])
            intent_doc = True
        # dose / frequency discrepancies
        charted_strength = med.strength
        charted_freq = med.regimen
        # A chart dose or frequency error is planted citing the GP line as the
        # truth, so it is only plantable where that line states the dose. A GP
        # list that says "as directed" (a phone-changed dose), or no GP line at
        # all, leaves nothing to contradict the chart: the finding would exist
        # only in the answer key. Same rule as the stale listings.
        comparable = (p.present["gp"] and med.gp_listing != "deleted"
                      and not med.changed_by_phone)
        if not comparable:
            pass
        elif rng.random() < HIDDEN_ERROR_RATES["emr"]["dose"]:
            halved = (dose or 0) / 2
            charted_strength = f"{halved:g} mg" if halved else med.strength
            plant("dose", med, ["emr", "gp"], [], {"charted": charted_strength,
                                                   "truth": med.strength},
                  "documented_intentional" if intent_doc else "likely_unintentional")
        elif rng.random() < HIDDEN_ERROR_RATES["emr"]["frequency"]:
            charted_freq = "1 daily" if "bd" in med.regimen else "1 bd"
            plant("frequency", med, ["emr", "gp"], [], {"charted": charted_freq,
                                                        "truth": med.regimen},
                  "likely_unintentional")
        row_id = rows.add("emr", dict(emr_base, record_kind="admission_chart",
                                      record_date=iso(AS_OF), med_name=med.generic,
                                      amt_mp_code=code_for(med, "amt_mp"),
                                      strength=charted_strength,
                                      dose=f"{strength_mg(charted_strength) or ''}",
                                      dose_unit="mg", route=med.route, frequency=charted_freq,
                                      chart_note=note, discharge_action="", action_reason=""))
        charted[med.generic] = row_id

    # commission (DATA_SPEC 5.2): charted but not current in truth
    ceased = [m for m in p.meds if not m.current]
    if ceased and rng.random() < 0.20:
        med = rng.choice(ceased)
        row_id = rows.add("emr", dict(emr_base, record_kind="admission_chart",
                                      record_date=iso(AS_OF), med_name=med.generic,
                                      amt_mp_code=code_for(med, "amt_mp"), strength=med.strength,
                                      dose=f"{strength_mg(med.strength) or ''}", dose_unit="mg",
                                      route=med.route, frequency=med.regimen, chart_note="",
                                      discharge_action="", action_reason=""))
        plant("commission", med, ["emr"], [row_id],
              {"ceased_on": iso(med.stop)}, "likely_unintentional")

    if p.prior_discharge:
        d_date = AS_OF - dt.timedelta(days=rng.randint(14, 180))
        for med in rng.sample(p.meds, min(len(p.meds), rng.randint(2, 4))):
            # The action has to agree with what actually happened. These were
            # drawn at random, so a discharge summary would "cease" a medicine
            # the patient carried on taking -- incoherent history that made a
            # current salbutamol inhaler and a current statin look like
            # commissions. A stopped medicine is ceased; a current one was
            # started or changed.
            if not med.current:
                action = "cease"
            else:
                action = pick(rng, (("start", 0.79), ("change", 0.21)))
            reason = "" if rng.random() > 0.81 else rng.choice(
                ["dose reduced: eGFR 28", "ceased: dizziness", "started: new AF"])
            rows.add("emr", dict(emr_base, record_kind="prior_discharge", record_date=iso(d_date),
                                 med_name=med.generic, amt_mp_code=code_for(med, "amt_mp"),
                                 strength=med.strength, dose=f"{strength_mg(med.strength) or ''}",
                                 dose_unit="mg", route=med.route, frequency=med.regimen,
                                 chart_note="", discharge_action=str(action), action_reason=reason))

    # -- GP -----------------------------------------------------------------
    if p.present["gp"]:
        given, family, dob_text = render_name_for("gp", p, rng, corruptions)
        updated = AS_OF - dt.timedelta(days=rng.randint(400, 500) if p.gp_doc_stale
                                       else rng.randint(1, 180))
        if p.gp_doc_stale:
            notices.append({"type": "stale_document", "source": "gp",
                            "detail": f"GP list updated {iso(updated)}"})
        gp_base = {"gp_pid": p.ids["gp"], "ihi_syn": ihi_for("gp", p, rng), "first_name": given,
                   "surname": family, "previous_surname": p.previous_surname,
                   "birth_date": ddmmyyyy(dt.date.fromisoformat(dob_text)), "gender":
                   "Female" if p.sex == "F" else "Male",
                   "postcode": postcode_for("gp", p, rng),
                   "last_reviewed": ddmmyyyy(updated), "list_last_updated": ddmmyyyy(updated)}
        for med in p.meds:
            if med.gp_listing == "deleted":
                continue
            # brand-vs-generic is a NEVER-FLAG negative control (DATA_SPEC 5.3)
            drug_text = (f"{med.brand} {med.strength}" if rng.random() < 0.35
                         else f"{med.generic} {med.strength}")
            directions = FREQ_WORDS.get(med.regimen, med.regimen)
            if med.changed_by_phone:
                directions = phone_dose_gp_directions(med, rng, directions)
            status = "active" if med.gp_listing == "active" else "ceased"
            row_id = rows.add("gp", dict(gp_base, drug_text=drug_text,
                                         amt_code=code_for(med, "amt_mpp"),
                                         strength=med.strength, directions=directions,
                                         status=status))
            # Only plantable when there is a pharmacy record to show the lapse.
            # possibly_ceased() reads the generator's own dispensing history,
            # which exists even for a patient with no pharmacy silo -- so a stale
            # listing was planted on evidence no silo contained, and no detector
            # could ever find it.
            if (status == "active" and not med.current and p.present["pharmacy"]
                    and med.possibly_ceased()):
                plant("stale_listing", med, ["gp", "pharmacy"], [row_id],
                      {"last_dispensed": iso(med.dispensings[-1]) if med.dispensings else None},
                      "likely_unintentional")
    else:
        notices.append({"type": "coverage_gap", "source": "gp", "detail": "no GP record found"})

    # -- Pharmacy -----------------------------------------------------------
    if p.present["pharmacy"]:
        given, family, dob_text = render_name_for("pharmacy", p, rng, corruptions)
        ph_base = {"cust_no": p.ids["pharmacy"], "ihi_syn": ihi_for("pharmacy", p, rng),
                   "name": f"{family.upper()}, {given}", "dob": dob_text,
                   "postcode": postcode_for("pharmacy", p, rng), "pharmacy_id": p.pharmacy_id}
        for med in p.meds:
            if med.hidden_at_second_pharmacy:
                continue
            for day in med.dispensings:
                rows.add("pharmacy", dict(
                    ph_base, dispensed_on=iso(day),
                    pbs_code="" if med.private else code_for(med, "pbs_code"),
                    brand=med.brand or med.generic, strength=med.strength, form=med.form,
                    qty=str(med.pack_qty), days_supply=str(med.days_supply),
                    repeats_left=str(rng.randint(0, med.pbs_repeats)),
                    script_type="private" if med.private else "PBS",
                    prescriber=f"Dr {rng.choice('ABCDEFGH')}. {rng.choice(SURNAMES)}-SYN"))
        # Overlay (DATA_SPEC 7): another person's dispensings under this customer
        # number. Linking this record correctly STILL yields a wrong medication
        # list, which is the whole point of surfacing it rather than resolving it.
        if p.overlay_from is not None:
            for med in p.overlay_from.meds[:3]:
                day = med.dispensings[-1] if med.dispensings else AS_OF
                overlay_ids.append(rows.add("pharmacy", dict(
                    ph_base, dispensed_on=iso(day),
                    pbs_code=code_for(med, "pbs_code"), brand=med.brand or med.generic,
                    strength=med.strength, form=med.form, qty=str(med.pack_qty),
                    days_supply=str(med.days_supply), repeats_left="0", script_type="PBS",
                    prescriber=f"Dr {rng.choice('ABCDEFGH')}. {rng.choice(SURNAMES)}-SYN")))
        if overlay_ids:
            # These rows belong to a different person. Recording the exact
            # row_ids means a tool that flags them is scored as CORRECT. Left
            # unlabelled, the overlay trap leaks into the data as an
            # unexplained ACE-inhibitor-plus-ARB or two-statin record, and the
            # tool is penalised for finding a real problem.
            notices.append({"type": "coverage_gap", "source": "pharmacy",
                            "row_ids": overlay_ids,
                            "detail": "overlay: these dispensings belong to another person"})
        if p.second_pharmacy:
            notices.append({"type": "possible_second_pharmacy", "source": "pharmacy",
                            "detail": "dispensing split across two pharmacies, one exposed"})
    else:
        notices.append({"type": "coverage_gap", "source": "pharmacy",
                        "detail": "no dispensing record found"})

    # -- Patient ------------------------------------------------------------
    if p.present["patient"]:
        given, family, dob_text = render_name_for("patient", p, rng, corruptions)
        pat_base = {"intake_id": p.ids["patient"], "ihi_syn": ihi_for("patient", p, rng),
                    "name_given": f"{given} {family}", "dob": dob_text}
        for med in p.meds:
            if rng.random() < HIDDEN_ERROR_RATES["patient"]["existence_omission"]:
                continue
            roll = rng.random()
            if roll < 0.25 and med.generic in LAY_TERMS:
                described = LAY_TERMS[med.generic]
            elif roll < 0.70:
                described = med.brand or med.generic
            elif roll < 0.90:
                described = med.generic
            else:
                described = "a little white one"
            still = ("yes" if med.current else
                     ("no" if rng.random() < 0.6 else "unsure"))
            how_often = FREQ_WORDS.get(med.regimen, med.regimen)
            if med.changed_by_phone:
                how_often = phone_dose_patient_words(med, rng)
            rows.add("patient", dict(pat_base, med_described=described,
                                     how_often=how_often, still_taking=still))
        for med in p.otc:
            row_id = rows.add("patient", dict(pat_base, med_described=med.generic,
                                              how_often="one a day", still_taking="yes"))
            notices.append({"type": "patient_only_item", "generic": med.generic,
                            "row_ids": [row_id], "detail": "OTC or complementary"})
    else:
        notices.append({"type": "coverage_gap", "source": "patient",
                        "detail": "no interview (delirium, no carer available)"})

    # -- bpmh_not_confirmable (ACSQHC 4.5) ----------------------------------
    found = sum(1 for s in ("gp", "pharmacy", "patient") if p.present[s])
    if found < 2:
        notices.append({"type": "bpmh_not_confirmable", "detail":
                        f"only {found + 1} of 4 sources found"})

    # -- duplication (DATA_SPEC 4.3) ----------------------------------------
    for med in p.meds:
        if len(med.ingredients) > 1:
            overlap = [m for m in p.meds if m is not med
                       and set(m.ingredients) & set(med.ingredients) and m.current]
            if overlap and med.current:
                plant("duplication", med, ["gp"], [],
                      {"overlaps_with": overlap[0].generic,
                       "shared": sorted(set(overlap[0].ingredients) & set(med.ingredients))},
                      "likely_unintentional")
    return planted, notices, corruptions


def apply_identity_traps(patients: list[Patient], split: dict[str, list[str]],
                         rng: random.Random) -> dict[str, list[dict[str, object]]]:
    """DATA_SPEC 7's deliberate linkage traps. Applied after building, before rendering.

    These exist to make the **false-merge rate** measurable, and a false merge is
    the worst thing this system can do: two patients' medicines blended into one
    list. Without decoys, Q1 returns only the patient's own records, every link
    is trivially correct, and a reported false-merge rate of zero means nothing.

    Trap families stay **inside one split**, so a pair cannot leak tuning
    information into held-out.

      lookalike_pair  3 per split. Same given name, surname and DOB; different
                      person, different IHI. The arithmetic cannot separate
                      them -- only a distinguishing field, or a human, can.
      twins           1 per split. Same surname, DOB and postcode, different
                      given names. Harder in one way: the names genuinely
                      differ, so a nickname match must not bridge them.
      overlay         1 per split. One pharmacy customer number holds some of
                      another person's dispensings, so linking the record
                      correctly still yields a wrong medication list.

    Returns `{patient_key: [trap, ...]}` for the ground truth. Every trap is
    `should_link: False`; any merge across one counts toward false-merge rate.
    """
    by_key = {p.key: p for p in patients}
    traps: dict[str, list[dict[str, object]]] = collections.defaultdict(list)

    def pair(kind: str, a: Patient, b: Patient, split_name: str, detail: str = "") -> None:
        for key, other in ((a.key, b), (b.key, a)):
            entry: dict[str, object] = {"kind": kind, "other_patient_key": other.key,
                                        "should_link": False, "split": split_name}
            if detail:
                entry["detail"] = detail
            traps[key].append(entry)

    for split_name, keys in split.items():
        pool = [by_key[k] for k in keys]
        if len(pool) < 10:
            continue
        chosen = rng.sample(pool, 10)

        for i in range(3):
            a, b = chosen[2 * i], chosen[2 * i + 1]
            b.given_name, b.family_name = a.given_name, a.family_name
            b.previous_surname = ""
            b.dob = a.dob
            b.nicknames = list(a.nicknames)
            # Copy the sex too. Otherwise the pair is separable on sex alone, so
            # the trap is toothless -- and it produces an implausible record
            # ("Thomas, F") that a pharmacist would notice before the linker did.
            b.sex = a.sex
            pair("lookalike_pair", a, b, split_name)

        a, b = chosen[6], chosen[7]
        b.family_name = a.family_name
        b.dob = a.dob
        b.postcode = a.postcode
        b.old_postcode = ""
        # Forcing the shared sex can strand b with a name of the other sex, so
        # rename whenever the name no longer fits -- not only on a collision.
        b_was = b.sex
        b.sex = a.sex
        if b.given_name == a.given_name or b_was != a.sex:
            if a.sex == "F":
                b.given_name = "Edith" if a.given_name != "Edith" else "Edna"
            else:
                b.given_name = "Edward" if a.given_name != "Edward" else "Ernest"
            b.nicknames = []
        pair("twins", a, b, split_name)

        host, donor = chosen[8], chosen[9]
        if host.present["pharmacy"] and donor.meds:
            host.overlay_from = donor
            pair("overlay", host, donor, split_name,
                 "one pharmacy customer number mixes two people")
    return dict(traps)


def resolve_row_ids(patient: Patient, rows: Rows, planted: list[dict[str, object]]) -> None:
    """Fill in each planted finding's `row_ids` once all four silos are written.

    Findings are planted while rendering the EMR, which happens before the GP,
    pharmacy and patient rows exist -- so the row ids simply are not known yet.
    They cannot be left empty: `docs/DATA_SPEC.md` 11.2 scores a true positive by
    **row_id overlap**, so a planted item with no row_ids can never be matched,
    and `safety.safety_gate` blocks any candidate that cannot cite its rows. An
    uncitable finding in the ground truth would quietly cap recall at zero for
    its whole type.
    """
    med_by_generic = {m.generic: m for m in patient.meds + patient.otc}
    for entry in planted:
        if entry["row_ids"]:
            continue
        generic = str(entry["generic"])
        med = med_by_generic.get(generic)
        brand = med.brand if med else ""
        wanted = {w.lower() for w in (generic, brand, LAY_TERMS.get(generic, "")) if w}
        found: list[str] = []
        for source in entry["sources_involved"] or list(SOURCES):  # type: ignore[union-attr]
            if not patient.present.get(source, False):
                continue
            pid = patient.ids[source]
            id_field = {"emr": "mrn", "gp": "gp_pid", "pharmacy": "cust_no",
                        "patient": "intake_id"}[source]
            text_field = {"emr": "med_name", "gp": "drug_text", "pharmacy": "brand",
                          "patient": "med_described"}[source]
            mine = [row for row in rows.data[source] if row.get(id_field) == pid]

            def exact(row: dict[str, str]) -> bool:
                # The term, then anything but "/": "amlodipine 5 mg" is the
                # single agent, "amlodipine/atorvastatin" is a different product.
                text = (row.get(text_field) or "").lower()
                return any(text.startswith(w) and text[len(w):len(w) + 1] != "/"
                           for w in wanted)

            def loose(row: dict[str, str]) -> bool:
                text = (row.get(text_field) or "").lower()
                return any(text.startswith(w) or w in text for w in wanted)

            match = next((r for r in mine if exact(r)), None) or next(
                (r for r in mine if loose(r)), None)
            if match is not None:
                found.append(match["row_id"])
        entry["row_ids"] = found


# --------------------------------------------------------------------------- #
# The harmonised view (DATA_SPEC 2.3) -- one definition, two consumers
# --------------------------------------------------------------------------- #

#: harmonised column -> {source: native column}, or a literal via ("=", value).
#: `scripts/register_sources.py` turns this into the `SELECT` list of each
#: `CREATE SCHEMASTORE VIEW`, and the fixtures below use it directly, so the
#: replayed envelopes and the live view cannot drift apart.
HARMONISED_MAP: dict[str, dict[str, object]] = {
    "source":            {s: ("=", s) for s in SOURCES},
    "row_id":            {s: "row_id" for s in SOURCES},
    "source_patient_id": {"emr": "mrn", "gp": "gp_pid", "pharmacy": "cust_no", "patient": "intake_id"},
    "ihi_syn":           {s: "ihi_syn" for s in SOURCES},
    "name_given":        {"emr": "given_name", "gp": "first_name", "pharmacy": "name", "patient": "name_given"},
    "name_family":       {"emr": "family_name", "gp": "surname"},
    "name_previous":     {"gp": "previous_surname"},
    "dob_text":          {"emr": "dob", "gp": "birth_date", "pharmacy": "dob", "patient": "dob"},
    "sex":               {"emr": "sex", "gp": "gender"},
    "postcode":          {"emr": "postcode", "gp": "postcode", "pharmacy": "postcode"},
    "record_kind":       {"emr": "record_kind", "gp": ("=", "gp_list"),
                          "pharmacy": ("=", "dispense"), "patient": ("=", "interview")},
    "doc_date":          {"emr": "record_date", "gp": "list_last_updated", "pharmacy": "dispensed_on"},
    "med_text":          {"emr": "med_name", "gp": "drug_text", "pharmacy": "brand", "patient": "med_described"},
    "med_code":          {"emr": "amt_mp_code", "gp": "amt_code", "pharmacy": "pbs_code"},
    "code_system":       {"emr": ("=", "amt"), "gp": ("=", "amt"), "pharmacy": ("=", "pbs")},
    "strength_text":     {"emr": "strength", "gp": "strength", "pharmacy": "strength"},
    "dose_text":         {"emr": "dose"},
    "route_text":        {"emr": "route", "pharmacy": "form"},
    "freq_text":         {"emr": "frequency", "gp": "directions", "patient": "how_often"},
    "status_text":       {"emr": "discharge_action", "gp": "status", "patient": "still_taking"},
    "note_text":         {"emr": "chart_note"},
    "qty":               {"pharmacy": "qty"},
    "days_supply":       {"pharmacy": "days_supply"},
    "pharmacy_id":       {"pharmacy": "pharmacy_id"},
    "script_type":       {"pharmacy": "script_type"},
}


def harmonise(source: str, row: dict[str, str]) -> dict[str, str | None]:
    """One native silo row -> the harmonised shape, matching the live view exactly.

    **`None` and `""` are different here, and the difference is load-bearing.**
    Verified against the registered views on 24 Oct:

      a column this source does NOT HAVE  -> the view emits CAST(NULL AS STRING)
                                             -> Zetaris returns JSON null
      a column it has, whose value is blank -> Zetaris returns ""

    So `name_family` is `None` for a pharmacy row (the silo has no such column at
    all, only a combined `name`), while `ihi_syn` is `""` for a patient whose IHI
    is simply missing. Both mean "absent" to `parse.py`, but flattening them here
    made every replayed envelope differ from the live view in 409 places -- the
    counts matched, so nothing failed, and `SAMPLE_MODE` would have quietly
    tested the wrong shape. Caught only by diffing against live.
    """
    out: dict[str, str | None] = {}
    for column in HARMONISED_COLUMNS:
        mapping = HARMONISED_MAP[column].get(source)
        if mapping is None:
            out[column] = None          # the source has no such column
        elif isinstance(mapping, tuple):
            out[column] = str(mapping[1])
        else:
            out[column] = str(row.get(mapping, "") or "")
    return out


def envelope(columns: tuple[str, ...], rows: list[dict[str, str | None]]) -> dict[str, object]:
    """A Zetaris response body.

    Every *present* value is a string; a `None` stays JSON null, because that is
    what the live view returns for a column the source does not have
    (`REFERENCE_NOTES` 1.1). Stringifying it would make the replayed envelope
    differ from live without changing any row count.
    """
    def cell(row: dict[str, str | None], column: str) -> str | None:
        value = row.get(column)
        return None if value is None else str(value)

    return {"headers": list(columns),
            "data": [[cell(r, c) for c in columns] for r in rows],
            "total": len(rows)}


def dob_variants(text: str) -> set[str]:
    """Every spelling Q1 blocks on. Mirrors `queries.dob_match_literals`."""
    out = {text}
    try:
        parsed = dt.date.fromisoformat(text)
    except ValueError:
        return out
    out.add(iso(parsed))
    out.add(ddmmyyyy(parsed))
    swapped = swap_day_month(parsed)
    if swapped:
        out.add(iso(swapped))
        out.add(ddmmyyyy(swapped))
    return out


def q1_matches(anchor: dict[str, str | None], row: dict[str, str | None]) -> bool:
    """The Q1 blocking predicate, in Python.

    Must stay equivalent to `queries.q_identity_candidates`. Step 6 verifies
    that by running the live query and diffing against these fixtures; any
    difference is a view bug or a drift between the two, never something to
    paper over.
    """
    if anchor["ihi_syn"] and row["ihi_syn"] == anchor["ihi_syn"]:
        return True
    if row["dob_text"] and row["dob_text"] in dob_variants(anchor["dob_text"] or ""):
        return True
    year = (anchor["dob_text"] or "")[:4]
    prefix = ""
    for char in (anchor["name_family"] or anchor["name_given"] or "").upper():
        if not (char.isalpha() or char in "'- "):
            break
        prefix += char
        if len(prefix) == 4:
            break
    if year and prefix and year in (row["dob_text"] or ""):
        for field in ("name_family", "name_previous", "name_given"):
            if (row.get(field) or "").upper().startswith(prefix):
                return True
    return row["source"] == anchor["source"] and row["source_patient_id"] == anchor["source_patient_id"]


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


# (generic, brand, strength) -> (PBS maximum quantity, PBS repeats). Filled by
# load_codes() from the lexicon, which built it from the real PBS item file.
PACKS: dict[tuple[str, str, str], tuple[int, int]] = {}


def load_codes() -> dict[tuple[str, str, str], dict[str, str]]:
    """(generic, brand, strength) -> its codes, from the built lexicon.

    Also fills PACKS, because the lexicon carries the real PBS
    ``maximum_quantity_units`` and ``number_of_repeats`` for every item. The
    generator used to guess a pack of 60 or 30, which made paracetamol 665 mg
    MR look like a 10-day supply and let it be dispensed 37 times a year.
    Med is constructed after this runs, so it can read the real number.
    """
    path = pathlib.Path("data/reference/lexicon.json")
    if not path.exists():
        log("  (no lexicon.json -- run `make lexicon` first; codes will be blank)")
        return {}
    records = json.loads(path.read_text())["records"]
    codes = {(r["generic"], r["brand"], r["strength"]): r for r in records}
    for key, r in codes.items():
        try:
            qty, repeats = int(r.get("pack_qty") or 0), int(r.get("repeats") or 0)
        except ValueError:
            continue
        if qty > 0:
            PACKS[key] = (qty, max(0, repeats))
    return codes


def load_nicknames() -> dict[str, tuple[list[str], str]]:
    """canonical -> (its variants, the sex it belongs to)."""
    out: dict[str, tuple[list[str], str]] = {}
    for row in read_csv(SRC / "nicknames.csv"):
        variants, _sex = out.get(row["canonical"], ([], row.get("sex", "F")))
        variants.append(row["variant"])
        out[row["canonical"]] = (variants, row.get("sex", "F"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patients", type=int, default=200,
                    help="total patients, split evenly tune/held-out (default 200)")
    ap.add_argument("--fixtures", type=int, default=10,
                    help="how many tune patients get Q1/Q2/Q3 fixtures")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--out-root", type=pathlib.Path, default=None,
                    help="write the silos and fixtures under this directory "
                         "instead of the repo (used by the determinism test, so "
                         "running the suite cannot overwrite committed data)")
    args = ap.parse_args()

    global OUT_ROOT
    if args.out_root is not None:
        OUT_ROOT = args.out_root

    products = [Product(r) for r in read_csv(SRC / "medicines.csv")]
    bundles: dict[str, list[Product]] = collections.defaultdict(list)
    for product in products:
        if product["bundle_id"] not in ("17", "18"):
            bundles[product["bundle_id"]].append(product)
    otc_products = [p for p in products if p["bundle_id"] == "18"]
    codes = load_codes()
    nicknames = load_nicknames()
    log(f"reference: {len(products)} products, {len(bundles)} bundles, "
        f"{len(otc_products)} OTC items, {len(codes)} lexicon codes")

    rows = Rows()
    dropped: list[str] = []
    patients: list[Patient] = []
    gt_patients: list[dict[str, object]] = []

    # Phase 1: build every patient. One stream per patient, derived from the
    # master seed, so adding a patient cannot change an earlier one's draws --
    # that is what keeps the tune/held-out split stable as the population grows.
    for index in range(1, args.patients + 1):
        rng = random.Random(args.seed * 100003 + index)
        p = Patient(index, rng, bundles, nicknames)
        p.induce_duplication(rng, products)
        for med in rng.sample(p.meds, min(len(p.meds), poisson(rng, CEASED_MEAN))):
            med.cease(rng)
        p.finalise(rng)
        if otc_products and rng.random() < PATIENT_ONLY_RATE:
            for product in rng.sample(otc_products, min(len(otc_products), 1 + int(rng.random() * 2))):
                p.otc.append(Med(product, rng))
        patients.append(p)

    half = args.patients // 2
    split = {"tune": [p.key for p in patients[:half]],
             "heldout": [p.key for p in patients[half:]]}

    # Phase 2: identity traps. These pair patients together, so they cannot be
    # applied while building them one at a time.
    traps = apply_identity_traps(patients, split, random.Random(args.seed + 7919))

    # Phase 3: render every patient into the four silos.
    for p in patients:
        rng = p.rng
        planted, notices, corruptions = render(p, rows, codes, rng)
        resolve_row_ids(p, rows, planted)
        # A planted finding with no citable row cannot be matched by DATA_SPEC
        # 11.2's row_id-overlap rule, so leaving it in the truth would cap that
        # type's recall below 1.0 for a reason that has nothing to do with the
        # detector. Dropped and counted, never silently kept.
        uncitable = [f for f in planted if not f["row_ids"]]
        dropped.extend(f"{p.key}:{f['type']}:{f['generic']}" for f in uncitable)
        planted = [f for f in planted if f["row_ids"]]
        gt_patients.append({
            "patient_key": p.key,
            "true_links": {s: [p.ids[s]] for s in SOURCES if p.present[s]},
            "coverage_truth": {
                "gp_present": p.present["gp"], "pharmacy_present": p.present["pharmacy"],
                "patient_present": p.present["patient"],
                "second_pharmacy_hidden": p.second_pharmacy,
                "private_script_items": sorted({m.generic for m in p.meds if m.private}),
                "prior_discharge": p.prior_discharge,
            },
            "corruptions": corruptions,
            "identity_traps": traps.get(p.key, []),
            "timeline": [{"generic": m.generic, "start": iso(m.start), "stop": iso(m.stop) or None,
                          "true_daily_dose_mg": m.true_daily_dose_mg,
                          "changed_by_phone": m.changed_by_phone} for m in p.meds],
            "planted": planted,
            "notices": notices,
        })

    # -- write silos --------------------------------------------------------
    out, fixtures_dir = OUT_ROOT / OUT, OUT_ROOT / FIXTURES
    (out / "silos").mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        payload = {"records": rows.data[source]}
        (out / "silos" / f"{source}.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
        log(f"  silo {source:9} {len(rows.data[source]):5} rows")

    ground_truth = {
        "seed": args.seed, "generator_version": GENERATOR_VERSION, "as_of": iso(AS_OF),
        "hidden_error_rates": HIDDEN_ERROR_RATES, "split": split, "patients": gt_patients,
    }
    (out / "ground_truth.json").write_text(json.dumps(ground_truth, indent=1), encoding="utf-8")

    # -- fixtures ----------------------------------------------------------
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    harmonised: list[dict[str, str]] = []
    for source in SOURCES:
        harmonised.extend(harmonise(source, r) for r in rows.data[source])

    written = 0
    for p in patients[:args.fixtures]:
        anchor = next((h for h in harmonised
                       if h["source"] == "emr" and h["source_patient_id"] == p.ids["emr"]), None)
        if anchor is None:
            continue
        q1 = [h for h in harmonised if q1_matches(anchor, h)]
        keys = {(s, p.ids[s]) for s in SOURCES if p.present[s]}
        q2 = [h for h in harmonised if (h["source"], h["source_patient_id"]) in keys]
        cited = {rid for entry in gt_patients[int(p.key[1:]) - 1]["planted"]  # type: ignore[index]
                 for rid in entry["row_ids"]}  # type: ignore[index]
        q3 = [h for h in harmonised if h["row_id"] in cited] or q2[:5]
        for name, cols, data in (("Q1", IDENTITY_COLUMNS, q1),
                                 ("Q2", HARMONISED_COLUMNS, q2),
                                 ("Q3", HARMONISED_COLUMNS, q3)):
            (fixtures_dir / f"{name}__{p.key}.json").write_text(
                json.dumps(envelope(cols, data), indent=1), encoding="utf-8")
            written += 1
    log(f"  fixtures: {written} envelopes for {min(args.fixtures, len(patients))} patients")

    # Q0: the admissions list, which is how a run finds its anchor. One envelope
    # for the whole population, exactly as queries.q_admissions() returns it --
    # one row per admission-chart LINE, so a caller dedupes on
    # source_patient_id. Without it, SAMPLE_MODE has nothing to replay for the
    # first query a run makes.
    q0 = [h for h in harmonised if h["source"] == "emr" and h["record_kind"] == "admission_chart"]
    (fixtures_dir / "Q0__admissions.json").write_text(
        json.dumps(envelope(IDENTITY_COLUMNS, q0), indent=1), encoding="utf-8")
    log(f"  fixtures: Q0__admissions.json, {len(q0)} rows, "
        f"{len({h['source_patient_id'] for h in q0})} admissions")

    # -- report ------------------------------------------------------------
    counts: collections.Counter = collections.Counter()
    notice_counts: collections.Counter = collections.Counter()
    for entry in gt_patients:
        for item in entry["planted"]:  # type: ignore[index]
            counts[item["type"]] += 1
        for item in entry["notices"]:  # type: ignore[index]
            notice_counts[item["type"]] += 1
    total_planted = sum(counts.values())
    log(f"\n{args.patients} patients, {sum(len(p.meds) for p in patients)} medicines, "
        f"{total_planted} planted ({total_planted / args.patients:.2f} per patient)")
    log("  planted by type:")
    for kind, n in counts.most_common():
        log(f"    {kind:32} {n}")
    log("  notices by type:")
    for kind, n in notice_counts.most_common():
        log(f"    {kind:32} {n}")
    missing = {"omission", "commission", "dose", "frequency", "duplication",
               "stale_listing", "dose_unconfirmable"} - set(counts)
    if missing:
        log(f"\n  NOT PLANTED in this run: {sorted(missing)}")
    if dropped:
        log(f"\n  dropped {len(dropped)} planted finding(s) with no citable row "
            f"(unscoreable by DATA_SPEC 11.2, so excluded rather than left to cap recall):")
        for item in dropped[:10]:
            log(f"    {item}")
    log(f"\n  split: {len(split['tune'])} tune / {len(split['heldout'])} held-out, "
        f"disjoint={not set(split['tune']) & set(split['heldout'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
