# Flow-Vul-Hunt Orbit Navigation Design

## Goal

将首页右侧关系图谱升级为 Flow-Vul-Hunt 的八模块导航：中心显示三行 `Flow / Vul / Hunt`，八个小圈对应左侧核心导航，hover 时平滑放大并显示模块介绍，点击后跳转到对应路由。

## Interaction

- 八个节点均为可聚焦、可点击的按钮，使用现有导航路由和图标。
- hover/focus 时暂停轨道旋转，节点放大、边框与光晕增强，说明面板显示标题、简介和进入提示。
- 点击或键盘 Enter/Space 触发 `navigate(to)`。
- 节点默认有轻微轨道和呼吸动画；动画受 `prefers-reduced-motion` 尊重。
- 小屏幕缩小图谱，节点仍可点击；说明面板在图谱下方显示，避免溢出。

## Architecture

继续使用 `HomePage.tsx` 中的 SVG 图谱，不引入第三方图谱依赖。将节点数据集中为一个带有 `to/icon/title/description/accent` 的数组，SVG 负责轨道、连线和装饰，HTML overlay 负责可访问的按钮和说明面板。路由沿用 React Router 和现有 `useNavigate`。

## Acceptance Criteria

1. 中心文本明确呈现 `Flow`、`Vul`、`Hunt` 三行。
2. 恰好渲染 8 个关系图谱节点，分别对应 8 个核心导航路由。
3. hover/focus 时节点有平滑缩放和光晕反馈，并显示对应简介。
4. 点击节点可跳转；键盘可访问。
5. `npm run build` 和 `npm run lint` 通过。

