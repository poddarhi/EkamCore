import { parseChatContent, parseModelList } from '../src/services/remote';

describe('parseModelList', () => {
  it('parses Ollama /api/tags', () => {
    const data = { models: [{ name: 'llama3.2:3b' }, { name: 'qwen2.5:7b' }] };
    expect(parseModelList('ollama', data)).toEqual(['llama3.2:3b', 'qwen2.5:7b']);
  });

  it('parses OpenAI /v1/models', () => {
    const data = { data: [{ id: 'gpt-oss-20b' }, { id: 'local-model' }] };
    expect(parseModelList('openai', data)).toEqual(['gpt-oss-20b', 'local-model']);
  });

  it('returns [] for malformed payloads', () => {
    expect(parseModelList('ollama', {})).toEqual([]);
    expect(parseModelList('openai', null)).toEqual([]);
  });
});

describe('parseChatContent', () => {
  it('reads Ollama chat content', () => {
    expect(
      parseChatContent('ollama', { message: { content: 'hi from ollama' } }),
    ).toBe('hi from ollama');
  });

  it('reads OpenAI chat content', () => {
    expect(
      parseChatContent('openai', {
        choices: [{ message: { content: 'hi from openai' } }],
      }),
    ).toBe('hi from openai');
  });

  it('returns empty string when absent', () => {
    expect(parseChatContent('ollama', {})).toBe('');
    expect(parseChatContent('openai', { choices: [] })).toBe('');
  });
});
