"""Quick read-only report of what's been collected."""

from __future__ import annotations

from sqlalchemy import select

from store import Case, CaseAdvocate, Advocate, Order, Session


def main() -> None:
    with Session() as s:
        print("=== Enriched cases (history fetched) ===")
        cases = s.scalars(select(Case).where(Case.history_fetched.is_(True))).all()
        for c in cases:
            advs = s.scalars(
                select(Advocate.name)
                .join(CaseAdvocate, CaseAdvocate.advocate_id == Advocate.id)
                .where(CaseAdvocate.case_id == c.id)
            ).all()
            orders = s.scalars(select(Order).where(Order.case_id == c.id)).all()
            print(f"\n  {c.case_number_full}  [{c.establishment}]")
            print(f"     {c.petitioner}  vs  {c.respondent}")
            print(f"     status={c.case_status!r}  disposal={c.nature_of_disposal!r}  decided={c.decision_date!r}")
            print(f"     judge={c.judge!r}")
            print(f"     advocates={advs}")
            for o in orders:
                print(f"     order#{o.order_number} {o.order_date} '{o.label}' downloaded={o.downloaded} -> {o.pdf_local_path}")

        print("\n=== Pending harvested seed names (self-expanding crawl) ===")
        from store import SeedName

        for sd in s.scalars(select(SeedName).where(SeedName.status == "pending")).all():
            print(f"   {sd.name!r}  (source={sd.source})")


if __name__ == "__main__":
    main()
