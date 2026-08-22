import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Search,
  Zap,
  Puzzle,
  X,
  ChevronRight,
  Power,
  PowerOff,
  BookOpen,
  User,
  Sparkles,
  Code,
  Database,
  Globe,
  Settings as SettingsIcon,
  Briefcase,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import apiClient, { type SkillInfo, type SkillDetail } from '../../lib/api';

// ── Category definitions ──
interface CategoryDef {
  key: string;
  label: string;
  icon: React.ElementType;
}

const CATEGORIES: CategoryDef[] = [
  { key: 'all', label: '全部', icon: Sparkles },
  { key: 'development', label: '开发', icon: Code },
  { key: 'system', label: '系统', icon: SettingsIcon },
  { key: 'data', label: '数据', icon: Database },
  { key: 'web', label: 'Web', icon: Globe },
  { key: 'productivity', label: '生产力', icon: Briefcase },
  { key: 'builtin', label: '内置', icon: Zap },
  { key: 'user', label: '自定义', icon: User },
];

// ── Fallback mock data (empty — show real API data or empty state) ──
const MOCK_SKILLS: SkillInfo[] = [];

// ── Props ──
interface SkillsPanelProps {
  open: boolean;
  onClose: () => void;
  activeSkills: string[];
  onToggleActive: (skillId: string) => void;
}

export function SkillsPanel({ open, onClose, activeSkills, onToggleActive }: SkillsPanelProps) {
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [skills, setSkills] = useState<SkillInfo[]>(MOCK_SKILLS);
  const [selectedDetail, setSelectedDetail] = useState<SkillDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [filterCategory, setFilterCategory] = useState('all');

  // Fetch skills from API
  const loadSkills = useCallback(async () => {
    setLoading(true);
    try {
      const apiSkills = await apiClient.fetchSkills();
      if (apiSkills && apiSkills.length > 0) {
        setSkills(apiSkills);
      }
    } catch {
      // API not available, keep mock data
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on open
  useEffect(() => {
    if (!open) return;
    loadSkills();
  }, [open, loadSkills]);

  // Fetch detail when selected
  useEffect(() => {
    if (!selectedId) {
      setSelectedDetail(null);
      return;
    }
    const skill = skills.find((s) => (s.name || s.id) === selectedId);
    if (!skill) return;

    // Try to get full detail from API
    apiClient.getSkill(skill.name).then((detail) => {
      setSelectedDetail(detail);
    }).catch(() => {
      // Fallback: construct a basic detail from SkillInfo
      setSelectedDetail({
        ...skill,
        content: '',
        tools: [],
      });
    });
  }, [selectedId, skills]);

  // Filter skills
  const filtered = useMemo(() => {
    return skills.filter((s) => {
      const matchSearch =
        !search ||
        s.name.toLowerCase().includes(search.toLowerCase()) ||
        s.description.toLowerCase().includes(search.toLowerCase()) ||
        s.triggers.some((t) => t.toLowerCase().includes(search.toLowerCase())) ||
        (s.tags && s.tags.some((t) => t.toLowerCase().includes(search.toLowerCase())));
      const matchCategory =
        filterCategory === 'all' ||
        s.category === filterCategory ||
        (filterCategory === 'builtin' && s.is_builtin) ||
        (filterCategory === 'user' && !s.is_builtin);
      return matchSearch && matchCategory;
    });
  }, [skills, search, filterCategory]);

  // Reset selectedId when category changes
  useEffect(() => {
    setSelectedId(null);
  }, [filterCategory]);

  const getSkillKey = (skill: SkillInfo) => skill.name || skill.id;
  const isSkillActive = (skill: SkillInfo) => activeSkills.includes(skill.name) || activeSkills.includes(skill.id);
  const selected = filtered.find((s) => getSkillKey(s) === selectedId) || filtered[0] || null;
  const selectedActive = selected ? isSkillActive(selected) : false;

  // Reload skills handler
  const handleReload = async () => {
    setReloading(true);
    try {
      await apiClient.reloadSkills();
      await loadSkills();
    } catch {
      // ignore
    } finally {
      setReloading(false);
    }
  };

  if (!open) return null;

  return (
    <div className="flex flex-col h-full bg-[var(--bg-primary)]">
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--hermes-border)] bg-[var(--bg-secondary)]">
          <div className="flex items-center gap-3">
            <Sparkles size={20} className="text-[var(--hermes-accent)]" />
            <h1 className="text-lg font-semibold text-text-primary">技能管理</h1>
            <span className="text-xs text-text-muted">
              {activeSkills.length} 已激活 · 技能是工作流提示，不是工具开关
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReload}
              disabled={reloading}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg text-text-secondary hover:text-text-primary hover:bg-[var(--bg-tertiary)] transition-colors border border-[var(--hermes-border)] disabled:opacity-50"
              title="重新加载技能"
            >
              <RefreshCw size={13} className={reloading ? 'animate-spin' : ''} />
              刷新
            </button>
          </div>
        </div>

        {/* Search + category filter */}
        <div className="px-5 py-3 border-b border-[var(--hermes-border)]">
          <div className="flex items-center gap-3 mb-2.5">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="搜索技能名称、描述、标签..."
                className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-[var(--bg-tertiary)] text-sm
                  text-text-primary placeholder-text-muted
                  border border-transparent focus:border-[var(--hermes-accent)] outline-none transition-colors"
              />
            </div>
            {loading && <Loader2 size={16} className="text-text-muted animate-spin" />}
          </div>
          {/* Category tabs */}
          <div className="flex items-center gap-1 flex-wrap">
            {CATEGORIES.map((cat) => {
              const Icon = cat.icon;
              return (
                <button
                  key={cat.key}
                  onClick={() => setFilterCategory(cat.key)}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs transition-colors ${
                    filterCategory === cat.key
                      ? 'bg-[var(--hermes-accent)]/15 text-[var(--hermes-accent)]'
                      : 'text-text-muted hover:text-text-secondary hover:bg-[var(--bg-tertiary)]'
                  }`}
                >
                  <Icon size={12} />
                  {cat.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Body: list + detail */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: skill list */}
          <div className="w-[300px] border-r border-[var(--hermes-border)] overflow-y-auto">
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-text-muted text-xs">
                <Puzzle size={24} className="mb-2 opacity-50" />
                未找到匹配的技能
              </div>
            ) : (
              <div className="py-1">
                {filtered.map((skill) => {
                  const skillKey = getSkillKey(skill);
                  const isActive = isSkillActive(skill);
                  const isSelected = selected ? getSkillKey(selected) === skillKey : false;
                  return (
                    <div
                      key={skillKey}
                      className={`flex items-center transition-all duration-150
                        ${isSelected
                          ? 'bg-[var(--hermes-accent)]/10 border-l-2 border-[var(--hermes-accent)]'
                          : 'border-l-2 border-transparent hover:bg-[var(--bg-tertiary)]'
                        }`}
                    >
                      <button
                        onClick={() => setSelectedId(skillKey)}
                        className="flex-1 text-left px-4 py-2.5 flex items-center gap-3"
                      >
                        <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors
                          ${isActive ? 'bg-[var(--hermes-accent)]/20' : 'bg-[var(--bg-tertiary)]'}`}>
                          {skill.is_builtin ? (
                            <Zap size={14} className={isActive ? 'text-[var(--hermes-accent)]' : 'text-text-muted'} />
                          ) : (
                            <User size={14} className={isActive ? 'text-[var(--hermes-accent)]' : 'text-text-muted'} />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <span className="text-sm font-medium text-text-primary truncate">
                              {skill.name}
                            </span>
                            {isActive && (
                              <span className="flex-shrink-0 w-1.5 h-1.5 rounded-full bg-[var(--hermes-accent)]" />
                            )}
                          </div>
                          <span className="text-xs text-text-muted truncate block">
                            {skill.description}
                          </span>
                        </div>
                      </button>
                      {/* Quick toggle button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleActive(skillKey);
                        }}
                        className={`flex-shrink-0 px-2 py-1 mr-2 rounded text-xs transition-colors
                          ${isActive
                            ? 'bg-[var(--hermes-accent)] text-white hover:opacity-80'
                            : 'bg-[var(--bg-tertiary)] text-text-muted hover:bg-[var(--bg-surface)]'
                          }`}
                        title={isActive ? '点击停用' : '点击激活'}
                      >
                        {isActive ? 'ON' : 'OFF'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: skill detail */}
          <div className="flex-1 overflow-y-auto">
            {selected ? (
              <div className="p-5 fade-in">
                {/* Title + toggle */}
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center
                      ${selectedActive
                        ? 'bg-[var(--hermes-accent)]/20'
                        : 'bg-[var(--bg-tertiary)]'
                      }`}>
                      {selected.is_builtin ? (
                        <Zap size={20} className={
                          selectedActive
                            ? 'text-[var(--hermes-accent)]'
                            : 'text-text-muted'
                        } />
                      ) : (
                        <User size={20} className={
                          selectedActive
                            ? 'text-[var(--hermes-accent)]'
                            : 'text-text-muted'
                        } />
                      )}
                    </div>
                    <div>
                      <h3 className="text-base font-semibold text-text-primary">{selected.name}</h3>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded
                          ${selected.is_builtin
                            ? 'bg-success/10 text-success'
                            : 'bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]'
                          }`}>
                          {selected.is_builtin ? <BookOpen size={10} /> : <User size={10} />}
                          {selected.is_builtin ? '内置' : '自定义'}
                        </span>
                        {selected.category && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-[var(--bg-tertiary)] text-text-muted">
                            {selected.category}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Enable / Disable toggle */}
                  <button
                    onClick={() => onToggleActive(getSkillKey(selected))}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200
                      ${selectedActive
                        ? 'bg-[var(--hermes-accent)] text-bg-primary hover:opacity-80'
                        : 'bg-[var(--bg-tertiary)] text-text-secondary hover:bg-[var(--bg-surface)] border border-[var(--hermes-border)]'
                      }`}
                  >
                    {selectedActive ? (
                      <>
                        <Power size={12} />
                        已激活
                      </>
                    ) : (
                      <>
                        <PowerOff size={12} />
                        激活
                      </>
                    )}
                  </button>
                </div>

                {/* Description */}
                <div className="mb-4">
                  <h4 className="text-xs font-medium text-text-muted mb-1.5 uppercase tracking-wider">描述</h4>
                  <p className="text-sm text-text-secondary leading-relaxed">{selected.description}</p>
                </div>

                {/* Tags */}
                {selected.tags && selected.tags.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-xs font-medium text-text-muted mb-1.5 uppercase tracking-wider">标签</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selected.tags.map((tag) => (
                        <span
                          key={tag}
                          className="inline-flex items-center px-2 py-0.5 rounded-md text-xs
                            bg-[var(--hermes-accent)]/10 text-[var(--hermes-accent)]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Triggers */}
                <div className="mb-4">
                  <h4 className="text-xs font-medium text-text-muted mb-1.5 uppercase tracking-wider">触发词</h4>
                  <div className="flex flex-wrap gap-1.5">
                    {selected.triggers.map((trigger) => (
                      <span
                        key={trigger}
                        className="inline-flex items-center px-2 py-0.5 rounded-md text-xs
                          bg-[var(--bg-tertiary)] text-text-secondary border border-[var(--hermes-border)]"
                      >
                        {trigger}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Tools (from detail) */}
                {selectedDetail?.tools && selectedDetail.tools.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-xs font-medium text-text-muted mb-1.5 uppercase tracking-wider">工具</h4>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedDetail.tools.map((tool) => (
                        <span
                          key={tool}
                          className="inline-flex items-center px-2 py-0.5 rounded-md text-xs
                            bg-success/10 text-success"
                        >
                          {tool}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Content preview */}
                {selectedDetail?.content && (
                  <div>
                    <h4 className="text-xs font-medium text-text-muted mb-1.5 uppercase tracking-wider">技能内容</h4>
                    <div className="p-3 rounded-lg bg-[var(--bg-tertiary)] border border-[var(--hermes-border)]">
                      <pre className="text-xs text-text-secondary whitespace-pre-wrap leading-relaxed font-mono">
                        {selectedDetail.content}
                      </pre>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-text-muted">
                <Sparkles size={32} className="mb-3 opacity-30" />
                <span className="text-sm">选择一个技能查看详情</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default SkillsPanel;
