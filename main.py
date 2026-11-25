"""Dip-and-pullback bot for the bars-replay/v1 harness.

Reads newline-delimited JSON on stdin (hello, then one batch per hourly
bar, then done) and prints exactly one reply line per batch on stdout.

Idea: Solana memecoins overreact downward on the hourly chart, so the bot
buys the dip and lets winners run a little.  A symbol is bought when its
14-bar RSI is deeply oversold (at or under 25), or when it is merely cheap
(RSI at or under 35) while still sitting above its 50-bar trend line.
A holding is sold in full as soon as momentum turns warm (RSI at or over
55) or the trade has moved 6% in either direction from its entry cost.
Positions are equal-weighted across the universe, capped by the harness
weight limit, and every order carries a 100 bps slippage bound.

Money is integers throughout; only the RSI and EMA indicators use floats.
Wire amounts go out as decimal strings, as the protocol schema requires.
Nothing here reads the clock, the environment, files, the network, or
unseeded randomness, so two runs on the same feed answer byte for byte.
"""

import json
import sys

SLIPPAGE_BPS = 100
RSI_LEN = 14
EMA_LEN = 50


def rsi_of(closes):
    """14-bar RSI from the latest closes, or None before 15 closes exist."""
    if len(closes) < RSI_LEN + 1:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - RSI_LEN, len(closes)):
        move = closes[i] - closes[i - 1]
        if move > 0:
            gains += move
        else:
            losses -= move
    avg_gain = gains / RSI_LEN
    avg_loss = losses / RSI_LEN
    if avg_loss == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)


class Tracker:
    """Close history plus a running 50-bar EMA for one symbol."""

    def __init__(self):
        self.closes = []
        self.ema = None

    def add(self, close):
        self.closes.append(close)
        n = len(self.closes)
        if n == EMA_LEN:
            self.ema = sum(self.closes) / EMA_LEN
        elif n > EMA_LEN:
            k = 2.0 / (EMA_LEN + 1)
            self.ema = close * k + self.ema * (1.0 - k)

    def rsi(self):
        return rsi_of(self.closes)

    def latest(self):
        return self.closes[-1] if self.closes else None


def main():
    order_no = 0
    hello = None
    order = []          # universe symbols, in hello order
    scales = {}         # symbol -> (price_scale, qty_scale)
    quote_scale = 6
    max_open = 10
    max_orders = 16
    max_weight_bps = 2500
    min_notional = 0
    warmup_bars = 0
    history = {}        # symbol -> Tracker

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        kind = msg.get("type")

        if kind == "hello":
            hello = msg
            order = [s["symbol"] for s in msg["symbols"]]
            scales = {s["symbol"]: (s["price_scale"], s["qty_scale"])
                      for s in msg["symbols"]}
            quote_scale = msg["capital"]["quote_scale"]
            max_open = msg["caps"]["max_open_positions"]
            max_orders = msg["caps"]["max_orders_per_bar"]
            max_weight_bps = msg["caps"]["max_weight_bps"]
            min_notional = int(msg["fees"]["min_notional_quote_units"])
            warmup_bars = msg.get("warmup_bars", 0)
            history = {sym: Tracker() for sym in order}
            continue

        if kind == "done":
            break

        if kind != "batch":
            continue

        seq = msg["seq"]
        for bar in msg["bars"]:
            sym = bar["symbol"]
            if sym in history:
                history[sym].add(int(bar["c"]))

        orders = []
        if seq >= warmup_bars:
            account = msg["account"]
            cash = int(account["cash_quote_units"])
            equity = int(account["equity_quote_units"])
            held = {}
            for pos in account["positions"]:
                qty = int(pos["qty"])
                if qty > 0:
                    held[pos["symbol"]] = (qty, int(pos["cost_quote_units"]))

            # Sells first, in universe order: whole position when momentum
            # turns warm or the trade moved 6% either way from its cost.
            freed_slots = 0
            for sym in order:
                if sym not in held:
                    continue
                qty, cost = held[sym]
                tracker = history[sym]
                close = tracker.latest()
                if close is None or cost <= 0:
                    continue
                price_scale, qty_scale = scales[sym]
                value = (qty * close * 10 ** quote_scale
                         // 10 ** (qty_scale + price_scale))
                rsi = tracker.rsi()
                if (rsi is not None and rsi >= 55
                        or value * 100 >= cost * 106
                        or value * 100 <= cost * 96):
                    order_no += 1
                    orders.append({"side": "sell", "client_id": "o%d" % order_no,
                                   "symbol": sym, "qty": str(qty),
                                   "max_slippage_bps": SLIPPAGE_BPS})
                    freed_slots += 1

            # Buys next, in universe order: oversold dip, or a cheap
            # pullback while the trend line still holds underneath.
            open_count = len(held) - freed_slots
            slots = min(len(order), max_open)
            stake = equity // slots if slots else 0
            weight_cap = max_weight_bps * equity // 10000
            cash_left = cash  # sells settle next bar; never fund buys here
            for sym in order:
                if len(orders) >= max_orders:
                    break
                if sym in held or open_count >= max_open:
                    continue
                tracker = history[sym]
                close = tracker.latest()
                if close is None:
                    continue
                rsi = tracker.rsi()
                if rsi is None:
                    continue
                ema = tracker.ema
                dip = rsi <= 25
                pullback = rsi <= 35 and ema is not None and close > ema
                if not (dip or pullback):
                    continue
                slice_ = min(stake, weight_cap, cash_left)
                if slice_ < min_notional:
                    continue
                order_no += 1
                orders.append({"side": "buy", "client_id": "o%d" % order_no,
                               "symbol": sym,
                               "notional_quote_units": str(slice_),
                               "max_slippage_bps": SLIPPAGE_BPS})
                cash_left -= slice_
                open_count += 1

        sys.stdout.write(json.dumps(
            {"type": "reply", "seq": seq, "orders": orders},
            separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
