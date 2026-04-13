# LR→RT 映射差异（grade.py 私有逻辑）

> 以下映射由 `grade.py` 的 `rt_map_*()` 函数实现。Curator 输出 Lightroom 标准参数，引擎自动转换。
> RT PP3 使用 (section, key) 格式，键名与 RawTherapee 实际格式一致。

| LR 参数          | RT PP3 Section.Key                                        | 映射行为                                     |
| ---------------- | --------------------------------------------------------- | -------------------------------------------- |
| exposure         | Exposure.Compensation                                     | x2.0 放大；负曝光同时提黑位 (Exposure.Black) |
| contrast         | Exposure.Contrast                                         | x0.8 缩放（RT 对比度更激进）                 |
| highlights (+)   | Exposure.HighlightCompr                                   | 正值 → HighlightCompr                        |
| highlights (-)   | HLRecovery.Enabled/Method/Hlbl                            | 负值 → 高光恢复 (Coloropp 方法)              |
| shadows (+)      | Exposure.ShadowCompr                                      | 正值 → ShadowCompr                           |
| shadows (-)      | Shadows & Highlights.Enabled/Shadows                      | 负值 → 阴影恢复                              |
| temp_offset      | White Balance.Temperature                                 | x0.5 偏移量                                  |
| tint_offset      | White Balance.Green                                       | 1.0 + tint × 0.005                           |
| vibrance         | Vibrance.Enabled/Pastels                                  | x0.9 缩放                                    |
| saturation       | Vibrance.Enabled/Saturated                                | x0.7 缩放                                    |
| tone_curve       | Exposure.Curve/CurveMode                                  | 10 点 CubicSpline 曲线                       |
| hsl (8 channels) | HSV Equalizer.Enabled/HueCurve/SatCurve/ValCurve          | 通道映射到色相环位置，生成 CubicSpline 曲线  |
| color_grading    | Color Toning.Enabled/Method/Shadows*\*/Highlights*\*      | Splitlr 方法；midtone → AutoCorrection       |
| sharpen          | Sharpening.Enabled/Method/DeconvRadius/DeconvAmount       | RL Deconvolution；amount x1.5，radius × 0.75 |
| noise_reduction  | Directional Pyramid Denoising.Enabled/Luma/Chroma/Ldetail | Lab 方法；gamma 1.4                          |
| vignette_amount  | Vignetting Correction.Amount/Radius/Strength              | abs(x) × 1.5                                 |
| grain_amount     | _(RT 无内置颗粒模块)_                                     | 记录为注释；无法映射到 RT                    |

### RT Section 与 PP3 键名对照

| RT Section                      | 示例键名                                                          | 说明                |
| ------------------------------- | ----------------------------------------------------------------- | ------------------- |
| [Version]                       | AppVersion, Version                                               | RT 版本标识         |
| [Exposure]                      | Compensation, Black, Contrast, HighlightCompr, ShadowCompr, Curve | 曝光与对比度        |
| [HLRecovery]                    | Enabled, Method, Hlbl                                             | 高光恢复            |
| [White Balance]                 | Temperature, Green, Equal                                         | 白平衡              |
| [Vibrance]                      | Enabled, Pastels, Saturated                                       | 自然饱和度          |
| [Color Management]              | ToneCurve, OutputBPC                                              | 色彩管理            |
| [HSV Equalizer]                 | HueCurve, SatCurve, ValCurve                                      | HSV 曲线调整        |
| [Color Toning]                  | Method, Shadows_Hue, Highlights_Hue                               | 色调分离            |
| [Sharpening]                    | Method, DeconvRadius, DeconvAmount                                | 锐化（RL 反卷积）   |
| [Directional Pyramid Denoising] | Enabled, Luma, Chroma, Ldetail                                    | 降噪（方向金字塔）  |
| [Vignetting Correction]         | Amount, Radius, Strength                                          | 暗角校正            |
| [Shadows & Highlights]          | Enabled, Shadows                                                  | 阴影/高光恢复       |
| [LensProfile]                   | LcMode, UseDistortion                                             | 镜头校正（lensfun） |
| [RAW]                           | HotPixelFilter, CA_AutoCorrect, DenoiseBlack                      | RAW 预处理          |
| [Output]                        | Format, Quality                                                   | 输出格式            |

### 参数换算示例

| LR 输入              | RT 实际值                        | 说明              |
| -------------------- | -------------------------------- | ----------------- |
| exposure: +0.5       | Exposure.Compensation: +1.0      | x2.0 放大         |
| contrast: +50        | Exposure.Contrast: +40           | x0.8 缩放         |
| highlights: -50      | HLRecovery.Hlbl: 50              | 负值 → 高光恢复   |
| shadows: +30         | Exposure.ShadowCompr: 30         | 正值 →ShadowCompr |
| sharpen: amount 80   | Sharpening.DeconvAmount: 120     | x1.5              |
| noise_reduction: 40  | DPD.Luma: 56, Chroma: 35         | Lab 方法          |
| vignette_amount: -40 | Vignetting Correction.Amount: 60 | abs(x) × 1.5      |
