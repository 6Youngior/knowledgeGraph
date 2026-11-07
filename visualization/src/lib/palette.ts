import type { RelationGroup } from '../types';

export const NODE_COLORS: Record<string, string> = {
  Company: '#38bdf8',
  Stock: '#f5b544',
  Model: '#a78bfa',
  Product: '#2dd4bf',
  Industry: '#94a3b8',
  Event: '#f472b6',
};

export const NODE_COLOR_FALLBACK = '#7dd3fc';

export const TYPE_ORDER = [
  'Event',
  'Model',
  'Company',
  'Product',
  'Stock',
  'Industry',
];

export const TYPE_LABEL: Record<string, string> = {
  Company: '公司',
  Stock: '证券',
  Model: '模型',
  Product: '产品',
  Industry: '行业',
  Event: '事件',
};

export const RELATION_LABEL: Record<string, string> = {
  DEVELOPED_BY: '研发主体',
  RELEASED_MODEL: '发布模型',
  LISTED_AS: '上市证券',
  PRODUCES: '提供产品',
  SUPPORTS_MODEL: '硬件适配',
  HOSTS_MODEL: '云服务接入',
  BELONGS_TO: '所属行业',
  UPSTREAM_OF: '上游供应',
  CONCERNS: '涉及实体',
  EVIDENCED_BY: '证据来源',
  PARTNER_OF: '商业合作',
};

export const GROUP_LABEL: Record<string, string> = {
  direct: '研发 / 上市',
  adaptation: '硬件适配',
  distribution: '云服务接入',
  industry: '行业分类',
};

export const GROUP_COLOR: Record<string, string> = {
  direct: '#5b8cff',
  adaptation: '#2dd4bf',
  distribution: '#c084fc',
  industry: '#94a3b8',
};

export const SOURCE_TYPE_LABEL: Record<string, string> = {
  official: '官方资料',
  official_site: '官方资料',
  announcement: '公司公告',
  exchange: '交易所资料',
  news: '财经新闻',
  research: '研究资料',
  report: '研究报告',
  press: '新闻稿',
  code_repository: '代码仓库',
  company_press_release: '公司新闻稿',
  company_report: '公司年报',
  exchange_quote: '交易所行情',
  exchange_announcement: '交易所公告',
  official_blog: '官方博客',
  official_docs: '官方文档',
  official_news: '官方新闻',
  press_release: '新闻稿',
  product_page: '产品页面',
  prospectus: '招股书',
  web: '公开网页',
};

export function nodeColor(type: string): string {
  return NODE_COLORS[type] ?? NODE_COLOR_FALLBACK;
}

export function typeLabel(type: string): string {
  return TYPE_LABEL[type] ?? type;
}

export function relationLabel(type: string, fallback?: string): string {
  return fallback || RELATION_LABEL[type] || type;
}

export function groupLabel(group?: string): string {
  if (!group) return '关系';
  return GROUP_LABEL[group] ?? group;
}

export function groupColor(group?: string): string {
  if (!group) return '#94a3b8';
  return GROUP_COLOR[group] ?? '#94a3b8';
}

export function sourceTypeLabel(type: string): string {
  return SOURCE_TYPE_LABEL[type] ?? type;
}

export const GROUP_OPTIONS: Array<{ value: 'all' | RelationGroup; label: string }> = [
  { value: 'all', label: '全部关系' },
  { value: 'direct', label: '研发 / 上市' },
  { value: 'adaptation', label: '硬件适配' },
  { value: 'distribution', label: '云服务接入' },
  { value: 'industry', label: '行业分类' },
];
