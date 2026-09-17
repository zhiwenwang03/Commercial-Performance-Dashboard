from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from threading import RLock

import numpy as np
import pandas as pd


SALES_STRING_COLUMNS = {
    "Region",
    "Sub Region",
    "Country",
    "Product Type",
    "Item - Item Group Full Name",
    "Customer - Name",
    "Item - Code",
    "Item number",
    "Cost center",
}


def _as_number(value):
    if value is None:
        return None
    if isinstance(value, (np.floating, float)) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return value


def _sorted_unique(frame: pd.DataFrame, column: str) -> list[str]:
    if frame.empty or column not in frame.columns:
        return []
    series = frame[column].dropna().astype(str).str.strip()
    series = series[series != ""]
    return sorted(series.unique().tolist())


def _read_all_sheets(file_bytes: bytes) -> pd.DataFrame:
    workbook = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
    if not workbook:
        return pd.DataFrame()
    return pd.concat(workbook.values(), ignore_index=True)


def _clean_sales_data(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    frame = frame.copy()
    frame.columns = frame.columns.str.strip()

    if "Year" in frame.columns and "Month" in frame.columns:
        frame["Date"] = pd.to_datetime(
            frame["Year"].astype(str) + "-" + frame["Month"].astype(str).str.zfill(2),
            format="%Y-%m",
            errors="coerce",
        ).dt.strftime("%Y-%m")
        frame = frame.drop(columns=["Year", "Month"])

    for column in frame.columns:
        if column in SALES_STRING_COLUMNS:
            frame[column] = frame[column].astype(str).str.strip()
        elif column != "Date":
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    if "Item - Item Group Full Name" in frame.columns:
        frame = frame[frame["Item - Item Group Full Name"] != "2900 - Packaging"]

    if "Country" in frame.columns:
        frame["Country"] = frame["Country"].astype(str).str.upper()
    if "Product Type" in frame.columns:
        frame["Product Type"] = frame["Product Type"].astype(str).str.upper()
    if "Item - Item Group Full Name" in frame.columns:
        frame["Item - Item Group Full Name"] = frame["Item - Item Group Full Name"].astype(str).str.upper()
    if "Customer - Name" in frame.columns:
        frame["Customer - Name"] = frame["Customer - Name"].astype(str).str.upper()

    if "Date" in frame.columns:
        frame["Date"] = frame["Date"].astype(str)
        frame = frame[~frame["Date"].isin(["nan", "None", "NaT"])]
        columns = ["Date"] + [column for column in frame.columns if column != "Date"]
        frame = frame[columns]

    return frame.reset_index(drop=True)


def _normalize_inventory_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    frame = frame.copy()
    frame.columns = frame.columns.str.strip()
    if "year_month" in frame.columns:
        frame["year_month"] = pd.to_datetime(frame["year_month"], errors="coerce").dt.strftime("%Y-%m")
    if "Item number" in frame.columns:
        frame["Item number"] = frame["Item number"].astype(str).str.upper().str.strip()
    if "category" in frame.columns:
        frame["category"] = frame["category"].astype(str).str.strip()
    return frame.reset_index(drop=True)


@dataclass
class DashboardStore:
    sales_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    inventory_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    pads_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    disc_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    moto_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    fluid_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    lock: RLock = field(default_factory=RLock)

    def reset(self) -> None:
        with self.lock:
            self.sales_df = pd.DataFrame()
            self.inventory_df = pd.DataFrame()
            self.balance_df = pd.DataFrame()
            self.pads_df = pd.DataFrame()
            self.disc_df = pd.DataFrame()
            self.moto_df = pd.DataFrame()
            self.fluid_df = pd.DataFrame()

    def load_uploads(self, uploads) -> dict:
        sales_frames: list[pd.DataFrame] = []

        with self.lock:
            self.inventory_df = pd.DataFrame()
            self.balance_df = pd.DataFrame()
            self.pads_df = pd.DataFrame()
            self.disc_df = pd.DataFrame()
            self.moto_df = pd.DataFrame()
            self.fluid_df = pd.DataFrame()

            for upload in uploads:
                filename = (upload.filename or "").lower()
                file_bytes = upload.read()
                if not file_bytes:
                    continue

                if "inventory" in filename:
                    self.inventory_df = _normalize_inventory_frame(_read_all_sheets(file_bytes))
                elif "balance" in filename:
                    self.balance_df = _normalize_inventory_frame(_read_all_sheets(file_bytes))
                elif "pads" in filename:
                    self.pads_df = _normalize_inventory_frame(_read_all_sheets(file_bytes))
                elif "disc" in filename:
                    self.disc_df = _normalize_inventory_frame(_read_all_sheets(file_bytes))
                elif "moto" in filename:
                    self.moto_df = _normalize_inventory_frame(_read_all_sheets(file_bytes))
                elif "fluid" in filename:
                    self.fluid_df = _normalize_inventory_frame(_read_all_sheets(file_bytes))
                else:
                    sales_frames.append(_clean_sales_data(pd.read_excel(io.BytesIO(file_bytes))))

            self.sales_df = pd.concat(sales_frames, ignore_index=True) if sales_frames else pd.DataFrame()

        return self.get_metadata()

    def get_metadata(self) -> dict:
        with self.lock:
            sales_df = self.sales_df.copy()
            inventory_df = self.inventory_df.copy()

        date_options = _sorted_unique(sales_df, "Date")
        months = _sorted_unique(inventory_df, "year_month")

        return {
            "salesLoaded": not sales_df.empty,
            "inventoryLoaded": not inventory_df.empty,
            "salesFilters": {
                "dateOptions": date_options,
                "regions": ["ALL Region", *_sorted_unique(sales_df, "Region")],
                "countries": ["ALL Country", *_sorted_unique(sales_df, "Country")],
                "productTypes": ["ALL Product Type", *_sorted_unique(sales_df, "Product Type")],
                "itemGroups": ["ALL Item Group", *_sorted_unique(sales_df, "Item - Item Group Full Name")],
                "customers": ["ALL Customer", *_sorted_unique(sales_df, "Customer - Name")],
                "itemCodes": ["ALL Item Code", *_sorted_unique(sales_df, "Item - Code")],
            },
            "inventoryFilters": {
                "months": months,
                "defaultMonth": months[-1] if months else None,
                "defaultStart": months[0] if months else None,
                "defaultEnd": months[-1] if months else None,
            },
        }

    def sales_dashboard(self, payload: dict) -> dict:
        with self.lock:
            sales_df = self.sales_df.copy()

        if sales_df.empty:
            return {
                "salesAmount": [],
                "salesQuantity": [],
                "unitPrice": [],
                "ebitPercent": [],
                "costBreakdowns": [],
            }

        currency = payload.get("currency", "RMB")
        aggregation = payload.get("aggregation", "monthly")
        include_revelia = bool(payload.get("includeRevelia", True))
        filters = payload.get("filters") or [self.default_sales_filter()]

        working = self._prepare_sales_currency_frame(sales_df, currency)
        response = {
            "salesAmount": [],
            "salesQuantity": [],
            "unitPrice": [],
            "ebitPercent": [],
            "costBreakdowns": [],
        }

        for index, filter_payload in enumerate(filters, start=1):
            label = filter_payload.get("label") or f"Filter {index}"
            filtered = self._apply_sales_filters(working, filter_payload, include_revelia)
            grouped = self._group_sales_frame(filtered, aggregation)

            response["salesAmount"].append({"name": label, "data": grouped["salesAmount"]})
            response["salesQuantity"].append({"name": label, "data": grouped["salesQuantity"]})
            response["unitPrice"].append({"name": label, "data": grouped["unitPrice"]})
            response["ebitPercent"].append({"name": label, "data": grouped["ebitPercent"]})
            response["costBreakdowns"].append({
                "name": label,
                "items": self._compute_cost_breakdown(filtered),
            })

        return response

    def inventory_overview(self, payload: dict) -> dict:
        with self.lock:
            inventory_df = self.inventory_df.copy()
            balance_df = self.balance_df.copy()
            pads_df = self.pads_df.copy()
            disc_df = self.disc_df.copy()

        if inventory_df.empty:
            return {"cards": [], "pie": []}

        selected_month = payload.get("month") or _sorted_unique(inventory_df, "year_month")[-1]
        pie_source = payload.get("pieSource", "Total")

        current_inventory = inventory_df[inventory_df["year_month"] == selected_month]
        previous_month = (pd.to_datetime(selected_month) - pd.DateOffset(months=1)).strftime("%Y-%m")
        previous_inventory = inventory_df[inventory_df["year_month"] == previous_month]
        current_balance = balance_df[balance_df.get("year_month", pd.Series(dtype=str)) == selected_month]
        previous_balance = balance_df[balance_df.get("year_month", pd.Series(dtype=str)) == previous_month]

        cards = self._inventory_cards(current_inventory, previous_inventory, current_balance, previous_balance)
        pie = self._inventory_pie(pie_source, selected_month, pads_df, disc_df)
        return {"cards": cards, "pie": pie}

    def inventory_dio(self, payload: dict) -> dict:
        with self.lock:
            inventory_df = self.inventory_df.copy()
            balance_df = self.balance_df.copy()
            sales_df = self.sales_df.copy()

        if inventory_df.empty:
            return {"points": []}

        start_date = payload.get("startDate")
        end_date = payload.get("endDate")
        category = payload.get("category", "Total Inventory")
        points = self._inventory_dio_points(inventory_df, balance_df, sales_df, start_date, end_date, category)
        return {"points": points}

    def inventory_coverage(self, payload: dict) -> dict:
        with self.lock:
            pads_df = self.pads_df.copy()
            disc_df = self.disc_df.copy()

        selected_month = payload.get("month")
        selected_source = payload.get("source", "Overall")
        if not selected_month:
            return {"pie": []}

        if selected_source == "Pads":
            working = pads_df
        elif selected_source == "Disc":
            working = disc_df
        else:
            working = pd.concat([pads_df, disc_df], ignore_index=True)

        if working.empty:
            return {"pie": []}

        filtered = working[
            (working.get("year_month") == selected_month)
            & (working.get("category", pd.Series(dtype=str)).astype(str).str.lower() == "normal")
        ].copy()

        if filtered.empty or "coverage" not in filtered.columns or "Inventory value" not in filtered.columns:
            return {"pie": []}

        labels = ["Other", "Less than 3m", "3-6m", "6-12m", "over1year", "no sales 6m"]
        filtered["cov_bin"] = pd.Categorical([pd.NA] * len(filtered), categories=labels, ordered=True)
        filtered.loc[np.isinf(filtered["coverage"]), "cov_bin"] = "no sales 6m"

        finite = (~np.isinf(filtered["coverage"])) & (filtered["coverage"] >= 0)
        filtered.loc[finite, "cov_bin"] = pd.cut(
            filtered.loc[finite, "coverage"],
            bins=[0, 3, 6, 12, float("inf")],
            labels=["Less than 3m", "3-6m", "6-12m", "over1year"],
            right=False,
        ).astype(str)
        filtered["cov_bin"] = filtered["cov_bin"].fillna("Other")

        coverage = (
            filtered.groupby("cov_bin", as_index=False)["Inventory value"]
            .sum()
            .rename(columns={"cov_bin": "label", "Inventory value": "value"})
        )
        return {
            "pie": [
                {"label": row["label"], "value": _as_number(row["value"])}
                for _, row in coverage.iterrows()
            ]
        }

    def default_sales_filter(self) -> dict:
        metadata = self.get_metadata()
        dates = metadata["salesFilters"]["dateOptions"]
        return {
            "label": "Filter 1",
            "startDate": dates[0] if dates else None,
            "endDate": dates[-1] if dates else None,
            "regions": ["ALL Region"],
            "countries": ["ALL Country"],
            "productTypes": ["ALL Product Type"],
            "itemGroups": ["ALL Item Group"],
            "customers": ["ALL Customer"],
            "itemCodes": ["ALL Item Code"],
        }

    def _prepare_sales_currency_frame(self, frame: pd.DataFrame, currency: str) -> pd.DataFrame:
        working = frame.copy()
        if currency == "EUR" and "RMB_rate" in working.columns:
            working["Adj Sales Amt"] = working["Total Sales Amt"] / working["RMB_rate"]
            working["Adj EBIT"] = working["EBIT"] / working["RMB_rate"]
            working["Adj Net Sales"] = working["Net Sales"] / working["RMB_rate"]
        elif currency == "USD" and {"RMB_rate", "USD_rate"}.issubset(working.columns):
            working["Adj Sales Amt"] = (working["Total Sales Amt"] / working["RMB_rate"]) * working["USD_rate"]
            working["Adj EBIT"] = (working["EBIT"] / working["RMB_rate"]) * working["USD_rate"]
            working["Adj Net Sales"] = (working["Net Sales"] / working["RMB_rate"]) * working["USD_rate"]
        else:
            working["Adj Sales Amt"] = working.get("Total Sales Amt", 0)
            working["Adj EBIT"] = working.get("EBIT", 0)
            working["Adj Net Sales"] = working.get("Net Sales", 0)
        return working

    def _apply_sales_filters(self, frame: pd.DataFrame, payload: dict, include_revelia: bool) -> pd.DataFrame:
        filtered = frame.copy()
        start_date = payload.get("startDate")
        end_date = payload.get("endDate")
        if start_date and "Date" in filtered.columns:
            filtered = filtered[filtered["Date"] >= start_date]
        if end_date and "Date" in filtered.columns:
            filtered = filtered[filtered["Date"] <= end_date]

        field_map = {
            "regions": ("Region", "ALL Region"),
            "countries": ("Country", "ALL Country"),
            "productTypes": ("Product Type", "ALL Product Type"),
            "itemGroups": ("Item - Item Group Full Name", "ALL Item Group"),
            "customers": ("Customer - Name", "ALL Customer"),
            "itemCodes": ("Item - Code", "ALL Item Code"),
        }

        for payload_key, (column, all_value) in field_map.items():
            values = payload.get(payload_key) or [all_value]
            if column in filtered.columns and all_value not in values:
                filtered = filtered[filtered[column].isin(values)]

        if not include_revelia and "Sub Region" in filtered.columns:
            filtered = filtered[filtered["Sub Region"].astype(str).str.upper() != "REVELIA"]

        return filtered

    def _group_sales_frame(self, frame: pd.DataFrame, aggregation: str) -> dict:
        required_columns = {"Adj Sales Amt", "Sales Qua", "Adj EBIT", "Adj Net Sales"}
        if frame.empty or not required_columns.issubset(frame.columns):
            return {
                "salesAmount": [],
                "salesQuantity": [],
                "unitPrice": [],
                "ebitPercent": [],
            }

        working = frame.copy()
        if aggregation == "yearly":
            working["bucket"] = pd.to_datetime(working["Date"], errors="coerce").dt.year.astype("Int64").astype(str)
        else:
            working["bucket"] = pd.to_datetime(working["Date"], errors="coerce").dt.strftime("%Y-%m")

        grouped = (
            working.dropna(subset=["bucket"])
            .groupby("bucket", as_index=False)
            .agg({
                "Adj Sales Amt": "sum",
                "Sales Qua": "sum",
                "Adj EBIT": "sum",
                "Adj Net Sales": "sum",
            })
            .sort_values("bucket")
        )

        if grouped.empty:
            return {
                "salesAmount": [],
                "salesQuantity": [],
                "unitPrice": [],
                "ebitPercent": [],
            }

        grouped["Unit Price"] = np.where(grouped["Sales Qua"] > 0, grouped["Adj Sales Amt"] / grouped["Sales Qua"], np.nan)
        grouped["EBIT %"] = np.where(grouped["Adj Net Sales"] > 0, grouped["Adj EBIT"] / grouped["Adj Net Sales"], np.nan)

        sales_mom = grouped["Adj Sales Amt"].pct_change().replace([np.inf, -np.inf], np.nan)
        quantity_mom = grouped["Sales Qua"].pct_change().replace([np.inf, -np.inf], np.nan)
        price_mom = grouped["Unit Price"].pct_change().replace([np.inf, -np.inf], np.nan)
        ebit_mom = grouped["EBIT %"].pct_change().replace([np.inf, -np.inf], np.nan)

        def build_points(value_column: str, mom_series: pd.Series) -> list[dict]:
            return [
                {
                    "x": row["bucket"],
                    "value": _as_number(row[value_column]),
                    "mom": _as_number(mom_series.iloc[index]),
                }
                for index, (_, row) in enumerate(grouped.iterrows())
            ]

        return {
            "salesAmount": build_points("Adj Sales Amt", sales_mom),
            "salesQuantity": build_points("Sales Qua", quantity_mom),
            "unitPrice": build_points("Unit Price", price_mom),
            "ebitPercent": build_points("EBIT %", ebit_mom),
        }

    def _compute_cost_breakdown(self, frame: pd.DataFrame) -> list[dict]:
        if frame.empty:
            return []

        total_sales = frame.get("Total Sales Amt", pd.Series(dtype=float)).sum()
        net_sales = frame.get("Net Sales", pd.Series(dtype=float)).sum()
        if total_sales == 0 or net_sales == 0:
            return []

        breakdown = [
            ("Rebate", frame.get("Rebate Amount", pd.Series(dtype=float)).sum() / net_sales),
            ("Freight Out", frame.get("Freight Out", pd.Series(dtype=float)).sum() / net_sales),
            ("Purchasing Material", frame.get("Act Material Cost Total", pd.Series(dtype=float)).sum() / net_sales),
            ("Warehouse Operation", frame.get("Contracted Work Total", pd.Series(dtype=float)).sum() / net_sales),
            ("Commission", frame.get("Commission", pd.Series(dtype=float)).sum() / net_sales),
            ("Other SG&A", frame.get("SG&A Total Exclud. Commission", pd.Series(dtype=float)).sum() / net_sales),
            ("EBIT", frame.get("EBIT", pd.Series(dtype=float)).sum() / net_sales),
        ]

        absolute_values = pd.Series([percentage * total_sales for _, percentage in breakdown], dtype=float).clip(lower=0)

        return [
            {
                "category": category,
                "percentage": _as_number(percentage),
                "absoluteValue": _as_number(absolute_values.iloc[index]),
            }
            for index, (category, percentage) in enumerate(breakdown)
        ]

    def _inventory_cards(self, current_inventory, previous_inventory, current_balance, previous_balance) -> list[dict]:
        def value_or_zero(frame, column):
            if frame.empty or column not in frame.columns:
                return 0.0
            return float(frame[column].sum())

        def mom(curr, prev):
            if prev in (0, None) or pd.isna(prev):
                return None
            return (curr - prev) / prev

        def sum_curr_prev(field, prefixes, current_df, previous_df, cost_centers=None):
            def compute(frame):
                if frame.empty or "Item number" not in frame.columns or field not in frame.columns:
                    return 0.0
                mask = frame["Item number"].astype(str).str.startswith(prefixes)
                if cost_centers and "Cost center" in frame.columns:
                    mask = mask & frame["Cost center"].isin(cost_centers)
                return float(frame.loc[mask, field].sum())

            return compute(current_df), compute(previous_df)

        total_amount = value_or_zero(current_balance, "1400-INVENTORY")
        total_amount_prev = value_or_zero(previous_balance, "1400-INVENTORY")
        git_raw_material_column = "102011001 - 在途物资—原材料 刹车盘"
        git_finished_disc_column = "102011101 - 在途物资—产成品 刹车盘"
        git_moto_column = "102011103 - 在途物资—产成品 MOTO"

        git_raw_material = value_or_zero(current_balance, git_raw_material_column)
        git_raw_material_prev = value_or_zero(previous_balance, git_raw_material_column)
        git_finished_disc = value_or_zero(current_balance, git_finished_disc_column)
        git_finished_disc_prev = value_or_zero(previous_balance, git_finished_disc_column)
        git_moto = value_or_zero(current_balance, git_moto_column)
        git_moto_prev = value_or_zero(previous_balance, git_moto_column)
        git_am_traditional = git_raw_material + git_finished_disc
        git_am_traditional_prev = git_raw_material_prev + git_finished_disc_prev
        git_total = git_am_traditional + git_moto
        git_total_prev = git_am_traditional_prev + git_moto_prev

        disc_qty, disc_qty_prev = sum_curr_prev("On-hand", ("08", "09", "14"), current_inventory, previous_inventory)
        disc_amt, disc_amt_prev = sum_curr_prev("Inventory value", ("08", "09", "14"), current_inventory, previous_inventory)
        pads_qty, pads_qty_prev = sum_curr_prev("On-hand", ("P", "S"), current_inventory, previous_inventory)
        pads_amt, pads_amt_prev = sum_curr_prev("Inventory value", ("P", "S"), current_inventory, previous_inventory)
        fluid_qty, fluid_qty_prev = sum_curr_prev("On-hand", ("L",), current_inventory, previous_inventory)
        fluid_amt, fluid_amt_prev = sum_curr_prev("Inventory value", ("L",), current_inventory, previous_inventory)

        moto_current = current_inventory[current_inventory.get("Cost center", pd.Series(dtype=str)).isin(["34N00037", "34N00039"])]
        moto_previous = previous_inventory[previous_inventory.get("Cost center", pd.Series(dtype=str)).isin(["34N00037", "34N00039"])]
        moto_qty = float(moto_current.get("On-hand", pd.Series(dtype=float)).sum())
        moto_qty_prev = float(moto_previous.get("On-hand", pd.Series(dtype=float)).sum())
        moto_amt = float(moto_current.get("Inventory value", pd.Series(dtype=float)).sum())
        moto_amt_prev = float(moto_previous.get("Inventory value", pd.Series(dtype=float)).sum())

        return [
            {"title": "Overall", "amount": total_amount, "quantity": None, "mom": mom(total_amount, total_amount_prev)},
            {"title": "Disc", "amount": disc_amt, "quantity": disc_qty, "mom": mom(disc_amt, disc_amt_prev)},
            {"title": "Pads", "amount": pads_amt, "quantity": pads_qty, "mom": mom(pads_amt, pads_amt_prev)},
            {"title": "Moto", "amount": moto_amt, "quantity": moto_qty, "mom": mom(moto_amt, moto_amt_prev)},
            {"title": "Fluid", "amount": fluid_amt, "quantity": fluid_qty, "mom": mom(fluid_amt, fluid_amt_prev)},
            {
                "title": "Goods In Transit",
                "amount": git_total,
                "quantity": None,
                "details": [
                    {"label": "AM Traditional", "value": git_am_traditional},
                    {"label": "Moto", "value": git_moto},
                ],
                "mom": mom(git_total, git_total_prev),
            },
        ]

    def _inventory_pie(self, pie_source, selected_month, pads_df, disc_df) -> list[dict]:
        if pie_source == "Pads":
            working = pads_df[pads_df.get("year_month") == selected_month]
        elif pie_source == "Disc":
            working = disc_df[disc_df.get("year_month") == selected_month]
        else:
            working = pd.concat([pads_df, disc_df], ignore_index=True)
            if not working.empty and "year_month" in working.columns:
                working = working[working["year_month"] == selected_month]

        if working.empty or "category" not in working.columns or "Inventory value" not in working.columns:
            return []

        pie_df = working.groupby("category", as_index=False)["Inventory value"].sum()
        return [
            {"label": row["category"], "value": _as_number(row["Inventory value"])}
            for _, row in pie_df.iterrows()
        ]

    def _inventory_dio_points(self, inventory_df, balance_df, sales_df, start_date, end_date, category) -> list[dict]:
        if not start_date or not end_date:
            months = _sorted_unique(inventory_df, "year_month")
            if not months:
                return []
            start_date = start_date or months[0]
            end_date = end_date or months[-1]

        def filter_by_category(frame: pd.DataFrame, column: str, selected: str) -> pd.DataFrame:
            if frame.empty:
                return frame
            if selected == "Moto":
                if "Cost center" not in frame.columns:
                    return pd.DataFrame()
                return frame[frame["Cost center"].isin(["34N00037", "34N00039"])]
            if column not in frame.columns:
                return frame
            values = frame[column].astype(str)
            if selected == "Pads":
                return frame[values.str.startswith(("2000", "P", "S"))]
            if selected == "Disc":
                return frame[values.str.startswith(("2330", "2300", "08", "09", "14"))]
            if selected == "Fluid":
                return frame[values.str.startswith("L")]
            return frame

        def add_balance_columns_to_inventory(summary_frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
            if balance_df.empty or "year_month" not in balance_df.columns:
                return summary_frame
            available_columns = [column for column in columns if column in balance_df.columns]
            if not available_columns:
                return summary_frame

            additions = balance_df[["year_month", *available_columns]].copy()
            additions["Balance Inventory Addition"] = additions[available_columns].apply(
                lambda row: pd.to_numeric(row, errors="coerce").fillna(0).sum(),
                axis=1,
            )
            additions = additions.groupby("year_month", as_index=False)["Balance Inventory Addition"].sum()
            merged = summary_frame.merge(additions, on="year_month", how="left")
            merged["Inventory value"] = (
                pd.to_numeric(merged.get("Inventory value"), errors="coerce").fillna(0)
                + pd.to_numeric(merged["Balance Inventory Addition"], errors="coerce").fillna(0)
            )
            return merged.drop(columns=["Balance Inventory Addition"]).sort_values("year_month")

        if category == "Total Inventory":
            if "1400-INVENTORY" in balance_df.columns and "year_month" in balance_df.columns and not balance_df.empty:
                summary = balance_df[
                    (balance_df["year_month"] >= start_date) & (balance_df["year_month"] <= end_date)
                ][["year_month", "1400-INVENTORY"]].copy()
                summary = (
                    summary.rename(columns={"1400-INVENTORY": "Inventory value"})
                    .groupby("year_month", as_index=False)["Inventory value"]
                    .sum()
                    .sort_values("year_month")
                )
            elif "Inventory value" in inventory_df.columns and "year_month" in inventory_df.columns:
                summary = (
                    inventory_df[
                        (inventory_df["year_month"] >= start_date) & (inventory_df["year_month"] <= end_date)
                    ]
                    .groupby("year_month", as_index=False)["Inventory value"]
                    .sum()
                    .sort_values("year_month")
                )
            else:
                summary = pd.DataFrame(columns=["year_month", "Inventory value", "Net Sales"])
            if "On-hand" in inventory_df.columns and "year_month" in inventory_df.columns:
                quantity = inventory_df.groupby("year_month", as_index=False)["On-hand"].sum()
                quantity = quantity[quantity["year_month"].between(start_date, end_date)]
                summary = summary.merge(quantity, on="year_month", how="left")
            filtered_sales = sales_df.copy()
        else:
            if category == "Moto":
                inv_filtered = filter_by_category(inventory_df, "Cost center", category)
                sales_filtered = filter_by_category(sales_df, "Cost center", category)
            elif category == "AM Traditional":
                if "Cost center" in inventory_df.columns:
                    inv_filtered = inventory_df[inventory_df["Cost center"] == "34N00001"].copy()
                else:
                    inv_filtered = pd.DataFrame()
                if "Cost center" in sales_df.columns:
                    sales_filtered = sales_df[sales_df["Cost center"] == "34N00001"].copy()
                else:
                    sales_filtered = pd.DataFrame()
            else:
                inv_filtered = filter_by_category(inventory_df, "Item number", category)
                if category in {"Pads", "Disc"} and "Cost center" in inv_filtered.columns:
                    inv_filtered = inv_filtered[inv_filtered["Cost center"] == "34N00001"].copy()

                sales_filtered = filter_by_category(sales_df, "Item - Code", category)
                if category in {"Pads", "Disc"} and "Cost center" in sales_filtered.columns:
                    sales_filtered = sales_filtered[sales_filtered["Cost center"] == "34N00001"].copy()

            if inv_filtered.empty or "year_month" not in inv_filtered.columns:
                summary = pd.DataFrame(columns=["year_month", "On-hand", "Inventory value"])
            else:
                summary = inv_filtered.groupby("year_month", as_index=False).agg({
                    "On-hand": "sum",
                    "Inventory value": "sum",
                }).sort_values("year_month")

            if category == "Moto":
                moto_in_transit_column = "102011103 - 在途物资—产成品 MOTO"
                if {"year_month", moto_in_transit_column}.issubset(balance_df.columns):
                    moto_in_transit = (
                        balance_df[["year_month", moto_in_transit_column]]
                        .groupby("year_month", as_index=False)[moto_in_transit_column]
                        .sum()
                        .rename(columns={moto_in_transit_column: "Moto In Transit"})
                    )
                    summary = summary.merge(moto_in_transit, on="year_month", how="left")
                    summary["Inventory value"] = (
                        pd.to_numeric(summary.get("Inventory value"), errors="coerce").fillna(0)
                        + pd.to_numeric(summary["Moto In Transit"], errors="coerce").fillna(0)
                    )
                    summary = summary.drop(columns=["Moto In Transit"]).sort_values("year_month")
            elif category == "AM Traditional":
                raw_material_column = "102011001 - 在途物资—原材料 刹车盘"
                finished_disc_column = "102011101 - 在途物资—产成品 刹车盘"
                required_columns = {"year_month", raw_material_column, finished_disc_column}
                if required_columns.issubset(balance_df.columns):
                    am_in_transit = balance_df[
                        ["year_month", raw_material_column, finished_disc_column]
                    ].copy()
                    am_in_transit["AM Traditional In Transit"] = (
                        pd.to_numeric(am_in_transit[raw_material_column], errors="coerce").fillna(0)
                        + pd.to_numeric(am_in_transit[finished_disc_column], errors="coerce").fillna(0)
                    )
                    am_in_transit = (
                        am_in_transit.groupby("year_month", as_index=False)["AM Traditional In Transit"]
                        .sum()
                    )
                    summary = summary.merge(am_in_transit, on="year_month", how="left")
                    summary["Inventory value"] = (
                        pd.to_numeric(summary.get("Inventory value"), errors="coerce").fillna(0)
                        + pd.to_numeric(summary["AM Traditional In Transit"], errors="coerce").fillna(0)
                    )
                    summary = summary.drop(columns=["AM Traditional In Transit"]).sort_values("year_month")
            if category in {"AM Traditional", "Disc"}:
                summary = add_balance_columns_to_inventory(
                    summary,
                    [
                        "102010301 - 在产品",
                        "102010801 - 产成品报废损失_刹车盘",
                    ],
                )
            filtered_sales = sales_filtered

        if not filtered_sales.empty and {"Date", "Net Sales"}.issubset(filtered_sales.columns):
            filtered_sales = filtered_sales.copy()
            filtered_sales["year_month"] = pd.to_datetime(filtered_sales["Date"], errors="coerce").dt.strftime("%Y-%m")
            monthly_sales = filtered_sales.groupby("year_month", as_index=False)["Net Sales"].sum()
            sales_dict = monthly_sales.set_index("year_month")["Net Sales"].to_dict()
            summary = summary.merge(monthly_sales, on="year_month", how="left")
        else:
            sales_dict = {}
            if "Net Sales" not in summary.columns:
                summary["Net Sales"] = 0.0

        if "Inventory value" not in summary.columns:
            summary["Inventory value"] = 0.0
        if "DIO Inventory value" not in summary.columns:
            summary["DIO Inventory value"] = summary["Inventory value"]
        if "Net Sales" not in summary.columns:
            summary["Net Sales"] = 0.0

        summary = summary[(summary["year_month"] >= start_date) & (summary["year_month"] <= end_date)].copy()
        if summary.empty:
            return []

        dio_values = []
        for _, row in summary.iterrows():
            try:
                dt_value = pd.to_datetime(row["year_month"])
                previous_months = [(dt_value - pd.DateOffset(months=offset)).strftime("%Y-%m") for offset in range(12)]
                total_sales = sum(sales_dict.get(month, 0) for month in previous_months)
                inventory_value = row.get("DIO Inventory value", 0)
                if inventory_value and total_sales > 0:
                    dio_values.append(round((inventory_value / total_sales) * 360, 2))
                else:
                    dio_values.append(None)
            except Exception:
                dio_values.append(None)

        summary["DIO"] = dio_values

        return [
            {
                "yearMonth": row["year_month"],
                "netSales": _as_number(row.get("Net Sales")),
                "inventoryValue": _as_number(row.get("Inventory value")),
                "dio": _as_number(row.get("DIO")),
            }
            for _, row in summary.iterrows()
        ]
