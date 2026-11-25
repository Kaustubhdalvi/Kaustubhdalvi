# Kaustubh Dalvi

My work in AI research engineering focuses on measuring what coding agents can do. I build reinforcement learning environments, run reproducible evaluations, and audit the Python graders. When a score surprises me, I trace the agent’s actions to see what the benchmark actually rewarded.

[Science puzzles](#science-puzzles) · [Coding challenge](#which-run-would-you-ship) · [LinkedIn](https://www.linkedin.com/in/kaustubhdalvi02/)

<picture>
  <source media="(prefers-reduced-motion: no-preference)" srcset="https://raw.githubusercontent.com/Kaustubhdalvi/Kaustubhdalvi/main/assets/pip-yard.gif">
  <img src="https://raw.githubusercontent.com/Kaustubhdalvi/Kaustubhdalvi/main/assets/pip-yard-rest.png" width="328" height="68" alt="Pip and two puppies trot through short grass, then nap beside their little doghouse and tree.">
</picture>

## Self portrait in type

<table align="center">
<tr><td>

```text
                                            .....       . .
                                  .:....:......   . .. . .  .   . .
                               .::...... . .   .       . .   .        . .
                            ::..       . . . .  . . . .   .   .       .   .
                           ;:  . .  ... .  .  .         . . . .  .  .   .  .
                          ::..    ........        ....:.::::::.      . .     .
                         ;... . ....... ... ....:..:::;;;;;;:;::...... ... . .
                        ::...................::::;++ccc+cc+cc+c++;:.:..........
                         :::...........:.:.:;;++ccccccccccccccccccc+:..:..... ..
                          :::.:....::::;:;+c+cccccccx*xxxxxxxxxxxxxcccc+;;:.....
                           .::.. ::::;;+ccccccccccxccxxx****xxxxxxx*xxxxccc;;:.
                             :.:..;:;;;c+c+cccccccxx*o&&oxccccxxxxxxxxcxcc+c++:+xxcc+
                              :::::;;;++cccccxxxxxooa*cccccx&&aoaoo***xxxcc;cx*&▒▒ao*x
                               .:::;;++cccxxx**o***xccccccxcccccccx***o**xc;xao*o&&*aac
                                 .;;;;c+++cc+cccc*a*xxxcccc+ccxxcx**o*oo*xxcc**oaxooo*
                                  :;:::+cc+cc+c;+coo**xxcccx***ooa&&aaoo**xxcca&▒axo&c
                                   ;+cccccc+cccc.cx***x**ooo***ooa&&&aaoo*xxcc***a*o&
                                    c+c;;c+ccxcc:cxx*o****ao*ooa&&@#&&oo**xxccxo##aa
                                    :c++cccxcxx+:cc****xxx*ao*o*a###&ao*o**xxccccc
                                     :cccccx*oo;;ccoaaooao**aaao*oooooo*o***xccc
                                      +++c**o#c;cccxoo*oo*x*oooooxx*ooaoooooxccxc
                                      :cccx*o&c;++:+ccccx*****xxc+c*aaoooaoxxccxx
                                       ;cccxxxccc+ccccccccxcccccxx*oo*oooo*xxcxc*
                                         ccccccc+;;++cccxx*ao*oaa&&aoooo**xxccx**c
                                          ++ccc**c;+cccxcxx*oaaa&aaaaa**xxccc*oooo
                                            ++cccxcccccxxcxx**oaaaaa*xccxcxc*oaooac
                                              ;+cccccxccxxx*o&#ao**ccccxxcx*o&&aaox
                                               :;;++c+ccx**xcxcccc+ccccxcx*&&&&a&ooc:
                                                .++;;:;;+cccc+cccccccxx**a&##&&&&&#c++
                                                ..:.:.:.;;++ccccccxxooooa&&#&#&#&▒ac;++:
                                               .+.:+++;;;:;+cccx*a&&&aaaa&###&#▒▒*+;;+;c+:
                                         ;++:.: ++;ccxxxccccccxx*oaa&&&&####&#▒oc::++;;ccc+:.
                                    +c+cc+cc::;..c;ccxxxxccccxx*ooa&########▒▒c;;;++;+c+c+c+.:......
                               +c+cc+cc+c+c+:;:; :c+ccx**o****oa&@@@@▒▒▒▒▒▒▒a+;;;+++cc+ccc+;::.:.:..:....
                          +c+cc+cc+cc+c+cc+c::;+: :++ccxccccccccc+c+cccc*aax::;;+c+c+cc++;;;;::.:.:..........
                     +c+cc+cc+c+c+c+cc+c+cc+c;;;+;:..::;;;;++..;;++;;;;:::..;;++c+cc+++;;;;+;;::.:.:.:..:.....
                 +cc+c+c+cc+cc+cc+cc+cccc+c++;;::;;+;;:::::;++:;;+c+++;;;;++cc+ccc++;;;;;;;;+;;:...:........:.
             ;cccc+c+ccc+c+c+cc+cc+cc+c++;;;;;+;;;;:;++++;;;;+;;c:+++;++c+cc++++;;;;;;;;;;;;;+;;::..:..:..:...
```

</td></tr>
</table>

## Science puzzles

### Astrophysics · A shadow across a star

Two small planets cross the center of the same star’s disk on circular, edge-on orbits. Treat each planet as a point. Their orbital periods are 8 and 27 days. The inner planet’s transit lasts 64 minutes. Approximate each crossing as a straight line at its mid-transit speed. **Does the outer planet take 64, 96, or 216 minutes?**

<details>
<summary>Reveal the transit time</summary>

**96 minutes.** Both shadows travel the same distance across the star. By Kepler’s third law, orbital radius scales as <i>P</i><sup>2/3</sup>, where P is the orbital period. Speed is circumference divided by period, so transit duration scales with the cube root of the period. The cube root of 27/8 is 3/2, and 64 × 3/2 = 96.

</details>

### Quantum computing · Two fair qubits

Prepare the Bell pair `(|00⟩ + |11⟩)/√2`. In one quarter of otherwise ideal trials, a phase flip (Z gate) hits the first qubit. Apply a Hadamard (H gate) to each qubit and measure both in the computational basis. Each individual bit looks perfectly fair. **Do the two bits match in half of the trials, in three quarters, or in all of them?**

<details>
<summary>Reveal the measurement odds</summary>

**3/4.** With no phase flip, the two Hadamards reproduce the initial Bell pair, yielding 00 or 11. A phase flip changes the plus sign to a minus. The Hadamards then give `(|01⟩ + |10⟩)/√2`, yielding opposite bits. Paired readings expose an error that inspecting either qubit alone would miss.

</details>

### Mathematics · A race between coin patterns

Toss a fair coin independently until either **HHT** or **HTH** appears for the first time in consecutive tosses. Both patterns have probability 1/8 in any fixed three-toss window. **Does HHT win with probability 1/3, 1/2, or 2/3?**

<details>
<summary>Reveal the winning odds</summary>

**2/3.** Start at the first H. If the next toss is H, the next T completes HHT. If the next two tosses are TH, HTH wins. If they are TT, you are back to waiting for a fresh H. Thus HHT wins on this attempt with probability 1/2, HTH wins with 1/4, and 1/4 starts the race over. The eventual chance of HHT winning is (1/2) ÷ (1 − 1/4) = 2/3.

</details>

[Check all three answers in Python](https://github.com/Kaustubhdalvi/Kaustubhdalvi/blob/main/examples/puzzle_checks.py).

## Which run would you ship?

Two weather feeds overlap at midnight. The readings below are invented for this puzzle. Merge them into UTC, expand `N` to `NORTH` and `S` to `SOUTH`, and collapse repeated reports for the same station and instant. Reject conflicting readings for one station and instant. Keep both stations when they report at the same time. Sort by instant, then station name. All times below have minute precision.

| Feed | First reading | Next reading |
| --- | --- | --- |
| Local · Jan 7 · UTC+05:30 | 05:28 · N · 4 °C | 05:30 · S · 7 °C |
| UTC · Jan 6–7 | 23:58 · NORTH · 4 °C | 00:00 · NORTH · 5 °C |

All three runs report three rows that add up to 16 °C. Pick one before opening the answer.

| Run | UTC output in order |
| --- | --- |
| **A** | Jan 7 00:00 NORTH 5°, SOUTH 7° · Jan 7 23:58 NORTH 4° |
| **B** | Jan 6 23:58 NORTH 4° · Jan 7 00:00 NORTH 5°, SOUTH 7° |
| **C** | Jan 6 23:58 NORTH 4° · Jan 7 00:00 NORTH 7°, SOUTH 5° |

<details>
<summary>Get a hint</summary>

What date is it in UTC when a station at UTC+05:30 reads 05:28 on January 7? Then check which station owns each value.

</details>

<details>
<summary>Reveal the answer and inspect the check</summary>

**Ship B.** Subtracting five hours and thirty minutes takes the first local reading back to January 6. Both feeds describe the same North reading then. At midnight the two stations really did record different temperatures. A shifts the date and C swaps their measurements. A check that counts three rows and sums their temperatures to 16 accepts all three.

Run <code>python3 examples/station_merge.py</code> from a copy of the repository to check all three candidates. [Inspect the Python verifier](https://github.com/Kaustubhdalvi/Kaustubhdalvi/blob/main/examples/station_merge.py).

</details>

If you’re working on coding-agent benchmarks, Harbor tasks, or verifier design, I’d like to compare failure cases. [Connect on LinkedIn](https://www.linkedin.com/in/kaustubhdalvi02/).
