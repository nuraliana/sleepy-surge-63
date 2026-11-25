# Strategy candidates considered

| Variant | Idea | Verdict |
| --- | --- | --- |
| Dip + pullback (CHOSEN) | Buy RSI(14) <= 25 outright, or RSI <= 35 while the close holds above EMA(50); exit whole position at RSI >= 55 or +/-6% from cost | Won: dev PnL +$362 on $10,000 capital (+$309 at 2x fees), max drawdown -0.38%, 36 trades, positive in every third of the dev window |
| Plain EMA crossover | Buy when a fast EMA crosses above a slow EMA, sell on the cross down | Lost: whipsawed by hourly memecoin chop; every crossover signal lagged the move it tried to catch |
| Plain buy-and-hold | Buy all seven symbols once and hold to the end | Lost: -$869 on dev; holds through every drawdown with no exit and no dip timing |
| RSI mean-reversion only | Buy RSI <= 30, sell RSI >= 70, no trend filter | Lost: caught falling knives in downtrends; the EMA(50) pullback filter in the chosen design is what keeps entries out of sustained slides |
| Momentum breakout | Buy fresh 20-bar highs, sell on 5% trailing stop | Lost: hourly breakouts on these symbols mostly fake out; entries paid top-of-range prices and the stops bled |

Why the chosen design won: it only buys after a sharp hourly selloff (deep RSI) or a cheap pullback inside an intact uptrend (RSI <= 35 above EMA-50), so entries get a discount instead of chasing; exits are tight and symmetric (+6% / -6% plus an RSI >= 55 momentum exit), so no single trade can sink the run; and equal-weight sizing across seven symbols keeps any one memecoin's drawdown small, which is why the max drawdown stays under half a percent.
