import { IconName } from '../components/Icon';

export interface ToolChoice {
  label: string;
  value: string;
}

export interface ToolOptionGroup {
  key: string;
  label: string;
  choices: ToolChoice[];
}

export interface ToolField {
  key: string;
  label: string;
  placeholder: string;
  hint?: string;
  multiline?: boolean;
  required?: boolean;
}

export interface ToolExample {
  label: string;
  values: Record<string, string>;
  opts?: Record<string, string>;
}

export type ToolCategory = 'Writing' | 'Productivity' | 'Business';

export interface Tool {
  id: string;
  title: string;
  tagline: string;
  /** One or two sentences explaining what the tool does and when to use it. */
  description: string;
  category: ToolCategory;
  icon: IconName;
  /** Two-stop gradient that gives each tool a recognizable identity. */
  accent: [string, string];
  cta: string;
  fields: ToolField[];
  options: ToolOptionGroup[];
  /** Optional one-tap presets that prefill the form so users "get it" fast. */
  examples?: ToolExample[];
  temperature?: number;
  maxTokens?: number;
  build: (
    values: Record<string, string>,
    opts: Record<string, string>,
  ) => { system: string; prompt: string };
}

export const CATEGORY_ORDER: ToolCategory[] = [
  'Writing',
  'Productivity',
  'Business',
];

const tone: ToolOptionGroup = {
  key: 'tone',
  label: 'Tone',
  choices: [
    { label: 'Professional', value: 'professional' },
    { label: 'Friendly', value: 'friendly' },
    { label: 'Formal', value: 'formal' },
    { label: 'Casual', value: 'casual' },
    { label: 'Persuasive', value: 'persuasive' },
  ],
};

const length: ToolOptionGroup = {
  key: 'length',
  label: 'Length',
  choices: [
    { label: 'Short', value: 'short' },
    { label: 'Medium', value: 'medium' },
    { label: 'Detailed', value: 'detailed' },
  ],
};

export const TOOLS: Tool[] = [
  {
    id: 'email-generator',
    title: 'Email Generator',
    tagline: 'Draft a polished email from a few notes',
    description:
      'Turn a quick note into a ready-to-send email — complete with subject line, greeting, body and sign-off, all in your chosen tone.',
    category: 'Writing',
    icon: 'mail',
    accent: ['#8B5CF6', '#6366F1'],
    cta: 'Generate email',
    fields: [
      {
        key: 'topic',
        label: 'What is the email about?',
        placeholder:
          'e.g. Ask my manager for 3 days leave next week for a family event',
        hint: 'Describe the goal in plain words — the more context, the better.',
        multiline: true,
        required: true,
      },
      {
        key: 'recipient',
        label: 'Recipient (optional)',
        placeholder: 'e.g. My manager, Sarah',
      },
    ],
    options: [tone, length],
    examples: [
      {
        label: 'Request time off',
        values: {
          topic: 'Ask my manager for 3 days off next week for a family event',
          recipient: 'My manager, Sarah',
        },
        opts: { tone: 'professional', length: 'short' },
      },
      {
        label: 'Follow up on a proposal',
        values: {
          topic:
            'Politely follow up on the proposal I sent last week and ask if they have questions',
          recipient: 'Client, Mr. Lee',
        },
        opts: { tone: 'friendly', length: 'medium' },
      },
    ],
    build: (v, o) => ({
      system:
        'You are an expert email writer. Write clear, well-structured emails with a subject line, greeting, body, and sign-off. Output only the email.',
      prompt: `Write an email.\nPurpose: ${v.topic}\n${
        v.recipient ? `Recipient: ${v.recipient}\n` : ''
      }Tone: ${o.tone}\nLength: ${o.length}\nInclude a clear subject line.`,
    }),
  },
  {
    id: 'email-reply',
    title: 'Email Reply Suggester',
    tagline: 'Get a great reply to an email you received',
    description:
      'Paste an email you received and get a thoughtful, ready-to-send reply — accept, decline or ask for more, all in the tone you want.',
    category: 'Writing',
    icon: 'reply',
    accent: ['#3B82F6', '#22D3EE'],
    cta: 'Suggest reply',
    fields: [
      {
        key: 'email',
        label: 'Paste the email you received',
        placeholder: 'Paste the full email here…',
        multiline: true,
        required: true,
      },
      {
        key: 'intent',
        label: 'What do you want to say back? (optional)',
        placeholder: 'e.g. Politely decline and propose next month instead',
        hint: 'Add a hint and the reply will follow your direction.',
        multiline: true,
      },
    ],
    options: [
      tone,
      {
        key: 'stance',
        label: 'Reply type',
        choices: [
          { label: 'Accept', value: 'accept the request' },
          { label: 'Decline', value: 'politely decline' },
          { label: 'Ask info', value: 'ask for more information' },
          { label: 'Acknowledge', value: 'acknowledge and confirm' },
        ],
      },
    ],
    examples: [
      {
        label: 'Confirm an interview',
        values: {
          email:
            'Hi, thanks for applying. Are you available for an interview this Tuesday at 2pm?',
          intent: 'Accept and confirm I am available',
        },
        opts: { tone: 'professional', stance: 'accept the request' },
      },
    ],
    build: (v, o) => ({
      system:
        'You write thoughtful, appropriate email replies. Output only the reply email, ready to send.',
      prompt: `Write a reply to this email.\n\n--- EMAIL ---\n${
        v.email
      }\n--- END ---\n\nGoal: ${o.stance}.\nTone: ${o.tone}.${
        v.intent ? `\nMy notes: ${v.intent}` : ''
      }`,
    }),
  },
  {
    id: 'meeting-summarizer',
    title: 'Meeting Notes Summarizer',
    tagline: 'Turn messy notes into a clean summary',
    description:
      'Drop in raw notes or a transcript and get a clean summary with clear action items — nothing invented, just what was said.',
    category: 'Productivity',
    icon: 'fileText',
    accent: ['#06B6D4', '#14B8A6'],
    cta: 'Summarize notes',
    temperature: 0.4,
    fields: [
      {
        key: 'notes',
        label: 'Paste meeting notes or transcript',
        placeholder: 'Paste raw notes, transcript, or bullet points…',
        multiline: true,
        required: true,
      },
    ],
    examples: [
      {
        label: 'Standup notes',
        values: {
          notes:
            '- discussed Q3 launch timeline\n- Sarah to finalize pricing by Friday\n- need design assets from Tom\n- Raj worried about server capacity\n- next sync Monday 10am',
        },
        opts: { format: 'summary-actions', length: 'medium' },
      },
    ],
    options: [
      {
        key: 'format',
        label: 'Format',
        choices: [
          { label: 'Summary + actions', value: 'summary-actions' },
          { label: 'Bullet summary', value: 'bullets' },
          { label: 'Action items only', value: 'actions' },
          { label: 'TL;DR', value: 'tldr' },
        ],
      },
      length,
    ],
    build: (v, o) => ({
      system:
        'You are an expert meeting assistant. Summarize accurately and never invent information that is not present.',
      prompt: `Summarize the following meeting notes.\nFormat: ${
        o.format === 'summary-actions'
          ? 'A short summary followed by a clear "Action items" list with owners if mentioned'
          : o.format === 'bullets'
          ? 'Concise bullet points'
          : o.format === 'actions'
          ? 'Only a list of action items with owners and due dates if mentioned'
          : 'A 2-3 sentence TL;DR'
      }.\nLength: ${o.length}.\n\n--- NOTES ---\n${v.notes}\n--- END ---`,
    }),
  },
  {
    id: 'text-rewriter',
    title: 'Text Rewriter',
    tagline: 'Rewrite, simplify, or fix any text',
    description:
      'Improve, simplify, shorten, expand or fix any text while keeping your original meaning intact.',
    category: 'Writing',
    icon: 'edit',
    accent: ['#EC4899', '#A855F7'],
    cta: 'Rewrite text',
    fields: [
      {
        key: 'text',
        label: 'Text to rewrite',
        placeholder: 'Paste the text you want to improve…',
        multiline: true,
        required: true,
      },
    ],
    examples: [
      {
        label: 'Fix a rough message',
        values: {
          text: 'we was hoping to maybe get the report done by friday if thats ok with everyone',
        },
        opts: { style: 'improve the writing and flow', tone: 'professional' },
      },
    ],
    options: [
      {
        key: 'style',
        label: 'Action',
        choices: [
          { label: 'Improve', value: 'improve the writing and flow' },
          { label: 'Simplify', value: 'simplify and make it easier to read' },
          { label: 'Shorten', value: 'make it more concise' },
          { label: 'Expand', value: 'expand with more detail' },
          { label: 'Fix grammar', value: 'fix grammar and spelling only' },
        ],
      },
      tone,
    ],
    build: (v, o) => ({
      system:
        'You are a skilled editor. Rewrite the user text as instructed and output only the rewritten text.',
      prompt: `Rewrite the following text: ${o.style}. Use a ${o.tone} tone.\n\n--- TEXT ---\n${v.text}\n--- END ---`,
    }),
  },
  {
    id: 'daily-planner',
    title: 'Daily Planner',
    tagline: 'Build a focused, time-blocked day',
    description:
      'List your tasks and get a realistic, time-blocked schedule with sensible priorities and short breaks built in.',
    category: 'Productivity',
    icon: 'calendar',
    accent: ['#F59E0B', '#FB923C'],
    cta: 'Plan my day',
    fields: [
      {
        key: 'tasks',
        label: 'Your tasks and goals',
        placeholder:
          'List everything you want to do today (one per line is fine)…',
        hint: 'One task per line works best.',
        multiline: true,
        required: true,
      },
      {
        key: 'hours',
        label: 'Available hours (optional)',
        placeholder: 'e.g. 9am–6pm with lunch at 1pm',
      },
    ],
    examples: [
      {
        label: 'A busy workday',
        values: {
          tasks:
            'Finish the slide deck\nGym session\nReply to client emails\nGrocery run\nRead 30 minutes',
          hours: '9am–6pm, lunch at 1pm',
        },
        opts: { focus: 'a balanced mix with breaks' },
      },
    ],
    options: [
      {
        key: 'focus',
        label: 'Style',
        choices: [
          { label: 'Balanced', value: 'a balanced mix with breaks' },
          { label: 'Deep work', value: 'long focused deep-work blocks' },
          { label: 'Light', value: 'a relaxed pace with buffer time' },
        ],
      },
    ],
    build: (v, o) => ({
      system:
        'You are a productivity coach. Create realistic, time-blocked daily schedules with short breaks.',
      prompt: `Create a time-blocked plan for my day with ${o.focus}.\n${
        v.hours ? `Available time: ${v.hours}.\n` : ''
      }Prioritize the tasks sensibly and add short breaks.\n\n--- TASKS ---\n${
        v.tasks
      }\n--- END ---\n\nReturn a schedule with time slots and a brief tip at the end.`,
    }),
  },
  {
    id: 'review-response',
    title: 'Review Response Writer',
    tagline: 'Reply to customer reviews with care',
    description:
      'Respond to customer reviews with a sincere, professional, on-brand message — never defensive, always considered.',
    category: 'Business',
    icon: 'star',
    accent: ['#10B981', '#34D399'],
    cta: 'Write response',
    fields: [
      {
        key: 'review',
        label: 'Paste the customer review',
        placeholder: 'Paste the review here…',
        multiline: true,
        required: true,
      },
      {
        key: 'business',
        label: 'Business name (optional)',
        placeholder: 'e.g. Bluebird Cafe',
      },
    ],
    examples: [
      {
        label: 'Reply to a complaint',
        values: {
          review:
            'Food was great but the service was slow and we waited 40 minutes to be seated.',
          business: 'Bluebird Cafe',
        },
        opts: { sentiment: 'negative', tone: 'professional' },
      },
    ],
    options: [
      {
        key: 'sentiment',
        label: 'Review type',
        choices: [
          { label: 'Positive', value: 'positive' },
          { label: 'Negative', value: 'negative' },
          { label: 'Mixed', value: 'mixed' },
        ],
      },
      tone,
    ],
    build: (v, o) => ({
      system:
        'You write professional, empathetic responses to customer reviews on behalf of a business. Be sincere, never defensive, and keep it concise. Output only the response.',
      prompt: `Write a response to this ${o.sentiment} customer review${
        v.business ? ` for ${v.business}` : ''
      }. Tone: ${o.tone}.\n\n--- REVIEW ---\n${v.review}\n--- END ---`,
    }),
  },
];

export function getTool(id: string): Tool | undefined {
  return TOOLS.find(t => t.id === id);
}

/** Tools grouped into their categories, in display order, skipping empties. */
export function toolsByCategory(): { category: ToolCategory; tools: Tool[] }[] {
  return CATEGORY_ORDER.map(category => ({
    category,
    tools: TOOLS.filter(t => t.category === category),
  })).filter(group => group.tools.length > 0);
}
