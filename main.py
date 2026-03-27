from pathlib import Path
import pandas as pd
import logging
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def load_all_csv_from_data(data_folder: str = "Data") -> pd.DataFrame:
    """
    Recursively find all .csv files under the given data folder (using absolute paths),
    read each into a DataFrame and return a single concatenated DataFrame.
    """
    data_dir = Path(data_folder).resolve()
    if not data_dir.exists() or not data_dir.is_dir():
        raise FileNotFoundError(f"`{data_dir}` does not exist or is not a directory")

    csv_files = sorted(data_dir.rglob("*.csv"))
    if not csv_files:
        logging.warning(f"No .csv files found under `{data_dir}`")
        return pd.DataFrame()

    frames = []
    for p in csv_files:
        try:
            logging.info(f"Reading `{p}`")
            df = pd.read_csv(p, sep=";")
            df['_source_path'] = str(p)  # optional: keep origin
            frames.append(df)
        except Exception as e:
            logging.warning(f"Skipping `{p}` due to read error: {e}")

    if not frames:
        logging.warning("No CSV files were successfully read")
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)
    logging.info(f"Combined {len(frames)} files into DataFrame with {len(combined)} rows")
    return combined


def validate_pm(df: pd.DataFrame) -> pd.DataFrame:
    # ─────────────────────────────────────────────
    # FLAG RIGHE VALIDE PER IL PARTICOLATO
    # ─────────────────────────────────────────────
    # Una riga è "valida per PM" solo se:
    #   - SDS_P2 non è NaN
    #   - umidità < 70% (sopra questa soglia l'SDS011 legge vapore acqueo come polvere)
    #     oppure umidità non disponibile (Humidity è NaN → non possiamo escluderla)
    # La seconda condizione è conservativa: se non hai il sensore umidità, tutte le
    # righe con SDS_P2 non-NaN sono considerate valide.

    if "Humidity" in df.columns:
        df["pm_valid"] = df["SDS_P2"].notna() & (df["Humidity"].isna() | (df["Humidity"] < 70))
    else:
        df["pm_valid"] = df["SDS_P2"].notna()

    # Versione "mascherata" di PM2.5 e PM10: NaN dove umidità > 70%
    # Queste colonne vengono usate per le aggregazioni orarie
    df["SDS_P2_valid"] = df["SDS_P2"].where(df["pm_valid"])
    df["SDS_P1_valid"] = df["SDS_P1"].where(df["pm_valid"])

    return df


def quality_flag(row):
    """Flag di affidabilità dell'ora:
    "good"     → ≥ 50% campioni ricevuti E ≥ 70% di quelli validi per PM
    "low_cov"  → pochi campioni ricevuti (WiFi giù, riavvii, ecc.)
    "humid"    → campioni ricevuti ma molti scartati per umidità
    "bad"      → entrambi i problemi
    "no_data"  → ora completamente vuota
    """
    if row["n_total"] == 0:
        return "no_data"
    cov_ok  = row["coverage_pct"] >= 50
    pm_ok   = row["pm_valid_pct"] >= 70
    if cov_ok and pm_ok:
        return "good"
    if not cov_ok and pm_ok:
        return "low_cov"
    if cov_ok and not pm_ok:
        return "humid"
    return "bad"


def aggregate_hourly(df: pd.DataFrame) -> pd.DataFrame:
    hourly = (
        df.resample("h", label="left", closed="left")
        .agg(

            # ── Particolato (solo righe valide per umidità) ──────────────────
            pm25_mean=("SDS_P2_valid", "mean"),  # media oraria PM2.5 → confronto normativo
            pm25_max=("SDS_P2_valid", "max"),  # picco dell'ora
            pm25_median=("SDS_P2_valid", "median"),  # mediana → robusta agli spike singoli
            pm25_std=("SDS_P2_valid", "std"),  # variabilità → rileva ore "nervose"

            pm10_mean=("SDS_P1_valid", "mean"),
            pm10_max=("SDS_P1_valid", "max"),

            # ── Temperatura e umidità (tutte le righe, anche con PM non valido) ─
            temp_mean=("Temp", "mean"),
            temp_min=("Temp", "min"),
            temp_max=("Temp", "max"),
            humidity_mean=("Humidity", "mean"),
            humidity_max=("Humidity", "max"),  # utile per capire perché ci sono buchi di PM

            # ── Segnale WiFi ────────────────────────────────────────────────────
            signal_mean=("Signal", "mean"),
            signal_min=("Signal", "min"),  # il minimo segnala rischio perdita dati

            # ── Contatori per la qualità dati ───────────────────────────────────
            n_total=("SDS_P2", "count"),  # righe totali nell'ora (anche con umidità alta)
            n_pm_valid=("SDS_P2_valid", "count"),  # righe con PM considerato affidabile
        )
    )
    # ─────────────────────────────────────────────
    # COLONNE DI QUALITÀ DATI
    # ─────────────────────────────────────────────
    # Percentuale di campioni ricevuti rispetto all'atteso teorico
    # < 50% → l'ora ha troppi buchi, la media oraria è poco rappresentativa
    hourly["coverage_pct"] = (hourly["n_total"] / EXPECTED_PER_HOUR * 100).clip(upper=100).round(1)

    # Percentuale di campioni validi per PM sul totale ricevuto
    # bassa → molte letture scartate per umidità alta
    hourly["pm_valid_pct"] = np.where(
        hourly["n_total"] > 0,
        (hourly["n_pm_valid"] / hourly["n_total"] * 100).round(1),
        np.nan,
    )
    hourly["quality"] = hourly.apply(quality_flag, axis=1)
    # Versione numerica del flag per filtrare facilmente nei passaggi successivi
    hourly["is_reliable"] = hourly["quality"] == "good"
    # ─────────────────────────────────────────────
    # COLONNE DERIVATE UTILI
    # ─────────────────────────────────────────────

    # Rapporto PM2.5/PM10: se > 0.8 → prevalenza di particolato fine (traffico, combustione)
    #                      se < 0.5 → prevalenza di particolato grossolano (polvere, vento)
    hourly["pm_ratio"] = (hourly["pm25_mean"] / hourly["pm10_mean"]).round(3)

    # Ora del giorno e giorno della settimana — utili per heatmap e pattern analysis
    hourly["hour"] = hourly.index.hour
    hourly["weekday"] = hourly.index.day_name()
    hourly["is_weekend"] = hourly.index.weekday >= 5

    return hourly


def aggregate_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    daily = (
        hourly.groupby(hourly.index.date)
        .apply(lambda g: pd.Series({

            # ── PM2.5 ────────────────────────────────────────────────────────
            # media ponderata: ore con più campioni validi pesano di più
            "pm25_mean": np.average(
                g["pm25_mean"].dropna(),
                weights=g.loc[g["pm25_mean"].notna(), "n_pm_valid"]
            ) if g["pm25_mean"].notna().any() else np.nan,

            "pm25_max":    g["pm25_max"].max(),       # max assoluto del giorno
            "pm25_median": g["pm25_median"].median(),  # mediana delle mediane orarie

            # ── PM10 ─────────────────────────────────────────────────────────
            "pm10_mean": np.average(
                g["pm10_mean"].dropna(),
                weights=g.loc[g["pm10_mean"].notna(), "n_pm_valid"]
            ) if g["pm10_mean"].notna().any() else np.nan,

            "pm10_max": g["pm10_max"].max(),

            # ── Temperatura e umidità ────────────────────────────────────────
            "temp_mean":     g["temp_mean"].mean(),    # media semplice va bene
            "temp_min":      g["temp_min"].min(),      # minimo dei minimi orari
            "temp_max":      g["temp_max"].max(),      # massimo dei massimi orari
            "humidity_mean": g["humidity_mean"].mean(),
            "humidity_max":  g["humidity_max"].max(),

            # ── WiFi ─────────────────────────────────────────────────────────
            "signal_mean": g["signal_mean"].mean(),
            "signal_min":  g["signal_min"].min(),

            # ── Contatori — si sommano ────────────────────────────────────────
            "n_total":    g["n_total"].sum(),
            "n_pm_valid": g["n_pm_valid"].sum(),

            # ── Qualità dati — si ricalcolano dai contatori ───────────────────
            # quante ore "good" sul totale delle ore con almeno un campione
            "n_hours_total":    (g["n_total"] > 0).sum(),
            "n_hours_good":     (g["quality"] == "good").sum(),
            "n_hours_humid":    (g["quality"] == "humid").sum(),
            "n_hours_low_cov":  (g["quality"] == "low_cov").sum(),
            "n_hours_no_data":  (g["quality"] == "no_data").sum(),

        }), include_groups=False)
    )

    # Indice come DatetimeIndex (comodo per il prossimo resample mensile)
    daily.index = pd.to_datetime(daily.index)

    daily["coverage_pct"]  = (daily["n_total"] / EXPECTED_PER_DAY * 100).clip(upper=100).round(1)
    daily["pm_valid_pct"]  = (daily["n_pm_valid"] / daily["n_total"] * 100).round(1)
    daily["hours_good_pct"] = (daily["n_hours_good"] / 24 * 100).round(1)

    daily["pm_ratio"] = (daily["pm25_mean"] / daily["pm10_mean"]).round(3)

    # Flag giornaliero affidabile: almeno 18 ore su 24 con qualità "good"
    daily["is_reliable"] = daily["n_hours_good"] >= 18
    return daily


def who_class(pm25):
    if pd.isna(pm25):
        return "no_data"
    if pm25 <= 5:
        return "who_2021"  # sotto limite annuo WHO 2021
    if pm25 <= 10:
        return "eu_2030"  # sotto futuro limite UE
    if pm25 <= 15:
        return "who_daily"  # sotto limite giornaliero WHO
    if pm25 <= 25:
        return "eu_current"  # sotto limite UE attuale
    return "above_all"  # sopra tutti i limiti


def aggregate_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        daily.resample("ME")  # ME = Month End, etichetta l'ultimo giorno del mese
        .apply(lambda g: pd.Series({
            # ── PM2.5 ────────────────────────────────────────────────────────
            # media ponderata sui soli giorni affidabili
            # è l'unica media confrontabile con i limiti normativi WHO/UE
            "pm25_mean": np.average(
                g.loc[g["is_reliable"], "pm25_mean"].dropna(),
                weights=g.loc[g["is_reliable"] & g["pm25_mean"].notna(), "n_pm_valid"]
            ) if g["is_reliable"].any() else np.nan,

            "pm25_max": g["pm25_max"].max(),
            "pm25_median": g["pm25_median"].median(),
            # ── PM10 ─────────────────────────────────────────────────────────
            "pm10_mean": np.average(
                g.loc[g["is_reliable"], "pm10_mean"].dropna(),
                weights=g.loc[g["is_reliable"] & g["pm10_mean"].notna(), "n_pm_valid"]
            ) if g["is_reliable"].any() else np.nan,

            "pm10_max": g["pm10_max"].max(),

            # ── Temperatura e umidità ────────────────────────────────────────
            "temp_mean": g["temp_mean"].mean(),
            "temp_min": g["temp_min"].min(),
            "temp_max": g["temp_max"].max(),
            "humidity_mean": g["humidity_mean"].mean(),

            # ── WiFi ─────────────────────────────────────────────────────────
            "signal_mean": g["signal_mean"].mean(),
            "signal_min": g["signal_min"].min(),

            # ── Contatori ────────────────────────────────────────────────────
            "n_total": g["n_total"].sum(),
            "n_pm_valid": g["n_pm_valid"].sum(),

            # ── Contatori giorni ─────────────────────────────────────────────
            "n_days_total": len(g),
            "n_days_reliable": g["is_reliable"].sum(),

            # Giorni sopra soglie normative — solo su giorni affidabili
            # altrimenti un giorno con dati mancanti potrebbe sembrare "pulito"
            "days_above_who_daily": (g.loc[g["is_reliable"], "pm25_mean"] > 15).sum(),
            "days_above_eu_current": (g.loc[g["is_reliable"], "pm25_mean"] > 25).sum(),
            "days_above_eu_2030": (g.loc[g["is_reliable"], "pm25_mean"] > 10).sum(),

        }))
    )
    monthly["coverage_pct"] = (monthly["n_days_reliable"] / monthly["n_days_total"] * 100).round(1)
    monthly["pm_ratio"] = (monthly["pm25_mean"] / monthly["pm10_mean"]).round(3)

    # Flag affidabilità mensile: almeno il 75% dei giorni del mese è reliable
    monthly["is_reliable"] = monthly["coverage_pct"] >= 75

    # Classificazione WHO 2021 sulla media mensile
    monthly["who_class"] = monthly["pm25_mean"].apply(who_class)
    return monthly


if __name__ == "__main__":
    EXPECTED_PER_HOUR = 22
    EXPECTED_PER_DAY = 541
    combined_df = load_all_csv_from_data("Data")
    # example: print summary
    print(combined_df.shape)
    combined_df = validate_pm(combined_df)
    combined_df["Time"] = pd.to_datetime(combined_df["Time"], format="%Y/%m/%d %H:%M:%S")
    combined_df = combined_df.set_index("Time").sort_index()
    hourly_df = aggregate_hourly(combined_df)
    print(hourly_df.shape)
    output_dir = Path("Output").resolve()
    hourly_df.to_csv(output_dir / "hourly_aggregated.csv")
    daily_df = aggregate_daily(hourly_df)
    print(daily_df.shape)
    daily_df.to_csv(output_dir / "daily_aggregated.csv")
    monthly_df = aggregate_monthly(daily_df)
    print(monthly_df.shape)
    monthly_df.to_csv(output_dir / "monthly_aggregated.csv")
