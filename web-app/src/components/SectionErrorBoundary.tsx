import { Component, type ErrorInfo, type ReactNode } from "react";

/** 错误边界输入：分区标题用于降级提示，onRetry 可选重试回调。 */
type Props = { children: ReactNode; title: string; onRetry?: () => void };
/** 错误边界状态：保存当前分区捕获到的渲染错误。 */
type State = { error: Error | null };

/**
 * 将单个页面分区的渲染错误隔离为友好空态，避免一个非关键组件让整个应用白屏。
 * 这是 React 错误边界，必须使用类组件才能实现 getDerivedStateFromError。
 * 只捕获子组件渲染期错误，不捕获事件处理、异步回调或边界自身的错误。
 */
export class SectionErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  /** 在错误渲染后的下一次提交中切换到降级界面。 */
  static getDerivedStateFromError(error: Error): State { return { error }; }  // 只捕获子组件渲染期错误，事件与异步错误不在此列
  /** 预留集中错误上报入口；当前不把实现细节或堆栈发送到客户界面。 */
  componentDidCatch(_error: Error, _info: ErrorInfo) {}

  render() {
    if (!this.state.error) return this.props.children; // 正常路径不增加额外 DOM 包裹，避免影响现有布局。
    return <section className="fyt-section-error" role="alert"><strong>{this.props.title}暂时无法显示</strong><p>可以先继续使用其他区域，稍后再试。</p>{this.props.onRetry ? <button type="button" onClick={() => { this.setState({ error: null }); this.props.onRetry?.(); }}>重新加载</button> : null}</section>;
  }
}

export default SectionErrorBoundary;
