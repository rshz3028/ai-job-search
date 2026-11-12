# Project Modules: choosing projects per application (since 2026-11-10)

Replaces the old rule "always the same 4 projects". The candidate's 4 real projects are split into **modules** (one aspect each) in `project_modules.json`. For each application, build the Projects section from the modules that best match the posting.

## Rules
1. **4 entries** on the CV (what the one-page `rishi-sidebar` layout holds). Use 3 if the page overflows.
2. **Drop whole projects that do not help.** For example, a power-electronics CV does not need ROS2/YOLOv8.
3. **At most 2 modules from the same project**, and they must not repeat each other's content. Do not use `mppt-converter` and `mppt-control` together, because the converter module already covers MPPT.
4. **Lead with the module closest to the posting.** Titles come from `titles_en`/`titles_fr`, or are reworded with the posting's term only when that term truly describes the work (see 03-writing-style.md, "Reframing boundaries").
5. **Each module keeps its own project's dates and origin line.** The entry `title` is the module title only (keep it under ~55 characters so it does not wrap into the dates). The entry `sub` is the project's `sub_en`/`sub_fr`, e.g. "Final-year project · 24 V solar MPPT charger". Two modules from one project then show the same origin and dates, so the split stays transparent. Never present them as separate jobs.
6. **No new facts.** Text may be shortened or reordered. New numbers, tools or results come only from `documents/RISHIKESH_PROFILE_EXPORT.md`. **The BMS is left out entirely** (candidate decision 2026-11-10): no BMS module, and no BMS in titles, sidebar skills, profile text or letters.
7. The cover letter can name module-level work ("the SEPIC power stage", "the P&O MPPT loop"). It must not contradict the CV titles.
8. Linux driver/kernel code stays in the skills section only, never as a module.

## Default mixes by role family (starting point, then adjust)
| Role family | Modules (in order) |
|---|---|
| Power electronics / converters | mppt-converter, mppt-pcb, bbw-testbench, imu-fusion |
| Control / estimation | mppt-control, imu-fusion, bbw-testbench, ros-nav |
| EV charging / battery-side power | mppt-converter, mppt-pcb, bbw-testbench, imu-fusion |
| Energy / electrical (grid, solar, buildings) | mppt-converter, mppt-pcb, bbw-testbench, imu-app |
| Hardware / electronics design | mppt-pcb, mppt-converter, bbw-testbench, imu-app |
| Test & validation | bbw-testbench, mppt-pcb (protections bench tests), imu-fusion (RMSE/MAE comparison), bbw-ml |
| Embedded firmware / automotive | bbw-testbench, bbw-ml, imu-app, mppt-converter |
| Embedded AI / edge ML | bbw-ml, ros-vision, bbw-testbench, imu-fusion |
| Robotics / ADAS / perception | ros-nav, ros-vision, imu-fusion, bbw-ml |
| Software / C++ tools | imu-app, imu-fusion, ros-nav, bbw-ml |

The Innspark OBD-II internship stays under Professional Experience in every mix. It is not a module.

## Interview note
Two CV entries from one project are honest as long as the candidate says they belong to the same project if asked, e.g. "both were parts of my final-year solar charger". Prepare one STAR story per module used.
