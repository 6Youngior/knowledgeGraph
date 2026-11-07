import { ArrowLeft, ArrowRight, PlayCircle, X } from 'lucide-react';

const STEPS = [
  {
    title: '查看事件与关联公司',
    text: '选中 GLM-5 发布，查看关联证券、产业角色和日期。',
  },
  {
    title: '打开关联路径',
    text: '点击一只证券，图中显示从事件到该证券的关系路径。',
  },
  {
    title: '查看原文与来源',
    text: '在右侧逐条查看关系原句、发布方和日期。',
  },
  {
    title: '切换历史日期',
    text: '选择历史日期，查看当时已记录的关联与行情。',
  },
  {
    title: '用新资料更新',
    text: '在知识更新中运行回放抽取，确认入图后回到本事件查看新增证券。',
  },
] as const;

export function DemoOverlay({
  step,
  onPrev,
  onNext,
  onClose,
}: {
  step: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const current = STEPS[step] ?? STEPS[0];
  const last = step === STEPS.length - 1;
  return (
    <div className="demo-overlay" role="dialog" aria-label="操作演示">
      <div className="demo-top">
        <span className="demo-badge"><PlayCircle size={14} /> 操作演示</span>
        <span className="demo-progress">第 {step + 1} / {STEPS.length} 步</span>
        <button type="button" className="demo-close" onClick={onClose} aria-label="结束演示">
          <X size={16} />
        </button>
      </div>
      <div className="demo-progress-bar">
        {STEPS.map((item, index) => (
          <i key={item.title} className={index <= step ? 'done' : ''} />
        ))}
      </div>
      <h3>{current.title}</h3>
      <p>{current.text}</p>
      <div className="demo-actions">
        <button type="button" className="button ghost" onClick={onPrev} disabled={step === 0}>
          <ArrowLeft size={14} /> 上一步
        </button>
        <button type="button" className="button primary" onClick={last ? onClose : onNext}>
          {last ? '结束' : '下一步'} {last ? null : <ArrowRight size={14} />}
        </button>
      </div>
    </div>
  );
}

export const DEMO_STEP_COUNT = STEPS.length;
