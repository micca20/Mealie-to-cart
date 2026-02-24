from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .http import HttpClient


@dataclass(frozen=True)
class ShoppingList:
    id: str
    name: str


@dataclass(frozen=True)
class MealieListItem:
    id: str
    note: str | None
    display: str
    quantity: float | None = None
    unit: str | None = None


class MealieClient:
    def __init__(self, *, mealie_url: str, api_key: str):
        self.http = HttpClient(base_url=mealie_url, token=api_key)

    def get_shopping_list_by_name(self, name: str) -> ShoppingList:
        lists = self.list_shopping_lists()
        for lst in lists:
            if lst.name.strip().lower() == name.strip().lower():
                return lst
        raise RuntimeError(f"Shopping list not found: {name}")

    def list_shopping_lists(self) -> list[ShoppingList]:
        # Mealie nightly uses /api/households/...; older versions used /api/groups/...
        for prefix in ("/api/households/shopping/lists", "/api/groups/shopping/lists"):
            try:
                data = self._get_json(prefix, params={"perPage": -1})
                items = data.get("items") or data.get("data") or data
                out: list[ShoppingList] = []
                for row in items:
                    _id = row.get("id") or row.get("uuid") or row.get("shoppingListId")
                    nm = row.get("name")
                    if _id and nm:
                        out.append(ShoppingList(id=str(_id), name=str(nm)))
                if out:
                    self._api_prefix = prefix.rsplit("/lists", 1)[0]
                    return out
            except RuntimeError:
                continue
        raise RuntimeError("No shopping lists returned (tried both /households/ and /groups/ endpoints)")

    def get_list_items(self, list_id: str) -> list[MealieListItem]:
        prefix = getattr(self, "_api_prefix", "/api/households/shopping")
        data = self._get_json(f"{prefix}/items", params={"perPage": -1, "shoppingListId": list_id})
        items = data.get("items") or data.get("data") or data
        out: list[MealieListItem] = []
        for row in items:
            _id = row.get("id") or row.get("uuid")
            note = row.get("note")
            # display text can vary; try multiple candidates
            display = (
                row.get("display")
                or row.get("text")
                or row.get("originalText")
                or row.get("food")
                or row.get("label")
                or ""
            )
            qty = row.get("quantity")
            unit = row.get("unit")
            if _id and display:
                out.append(
                    MealieListItem(
                        id=str(_id),
                        note=str(note) if note is not None else None,
                        display=str(display),
                        quantity=float(qty) if isinstance(qty, (int, float)) else None,
                        unit=str(unit) if unit is not None else None,
                    )
                )
        return out

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self.http.get(path, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(f"Mealie API error {resp.status_code} for {path}: {resp.text[:500]}")
        try:
            return resp.json()
        except Exception as e:
            raise RuntimeError(f"Failed to decode JSON from Mealie for {path}: {e}")
