import React, { useState, useEffect } from 'react';
import { Zap, Search, ChevronRight, Loader2 } from 'lucide-react';
import { getBackendUrl } from '../../lib/utils';

interface Skill {
  name: string;
  description: string;
  triggers: string[];
}

export function SkillsPanel() {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [matchedSkills, setMatchedSkills] = useState<Skill[]>([]);

  useEffect(() => {
    loadSkills();
  }, []);

  const loadSkills = async () => {
    try {
      const res = await fetch(`${getBackendUrl()}/api/skills`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // API 返回数组格式 [{name, description, triggers}]
      setSkills(Array.isArray(data) ? data : (data.skills || []));
    } catch (err) {
      console.error('Failed to load skills:', err);
    }
    setLoading(false);
  };

  const searchSkills = async () => {
    if (!searchQuery.trim()) {
      setMatchedSkills([]);
      return;
    }
    try {
      const res = await fetch(`${getBackendUrl()}/api/skills/match`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // API 返回数组格式 [{name, description, triggers}]
      setMatchedSkills(Array.isArray(data) ? data : (data.skills || []));
    } catch (err) {
      console.error('Failed to search skills:', err);
    }
  };

  useEffect(() => {
    const timer = setTimeout(searchSkills, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const displaySkills = searchQuery.trim() ? matchedSkills : skills;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 size={24} className="animate-spin text-accent" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-4">
        <Zap size={20} className="text-accent" />
        <h3 className="text-lg font-semibold text-text-primary">技能库</h3>
        <span className="text-xs text-text-muted bg-bg-tertiary px-2 py-0.5 rounded-full">
          {skills.length} 个技能
        </span>
      </div>

      <p className="text-sm text-text-muted">
        AI 会根据你的问题自动加载相关技能。以下是可用的技能列表。
      </p>

      {/* Search */}
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-muted" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="搜索技能..."
          className="w-full pl-10 pr-4 py-2 bg-bg-primary text-text-primary text-sm rounded-lg outline-none border border-border focus:border-accent transition-colors"
        />
      </div>

      {/* Skills list */}
      <div className="space-y-2 max-h-[400px] overflow-y-auto">
        {displaySkills.map((skill) => (
          <div
            key={skill.name}
            className="p-3 rounded-lg border border-border hover:border-accent/50 transition-colors group"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap size={14} className="text-accent" />
                <span className="text-sm font-medium text-text-primary">
                  {skill.name}
                </span>
              </div>
              <ChevronRight size={14} className="text-text-muted group-hover:text-accent transition-colors" />
            </div>
            <p className="text-xs text-text-muted mt-1 ml-6">
              {skill.description}
            </p>
            <div className="flex flex-wrap gap-1 mt-2 ml-6">
              {skill.triggers.slice(0, 5).map((trigger) => (
                <span
                  key={trigger}
                  className="px-2 py-0.5 text-xs bg-bg-tertiary text-text-secondary rounded"
                >
                  {trigger}
                </span>
              ))}
              {skill.triggers.length > 5 && (
                <span className="text-xs text-text-muted">
                  +{skill.triggers.length - 5}
                </span>
              )}
            </div>
          </div>
        ))}
        {displaySkills.length === 0 && (
          <div className="text-center py-8 text-text-muted text-sm">
            {searchQuery ? '没有找到匹配的技能' : '暂无技能'}
          </div>
        )}
      </div>
    </div>
  );
}
