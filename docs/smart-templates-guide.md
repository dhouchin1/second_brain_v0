# Smart Templates User Guide

## Overview

Smart Templates is an AI-powered note structuring system that helps you create professional, consistent notes with minimal effort. Whether you're capturing meeting notes, planning projects, or documenting ideas, Smart Templates provides context-aware suggestions and customizable templates to accelerate your workflow.

## 🚀 Quick Start

### Accessing Smart Templates
1. Navigate to your Second Brain dashboard
2. Look for the **purple "Smart Templates" button** in the quick capture area
3. Click to open the Smart Templates modal

### Using Pre-built Templates
1. **Browse Available Templates**: 5 professional templates are ready to use
2. **Search Templates**: Use the search box to find specific types (try "meeting", "project", "idea")
3. **Apply Templates**: Click "Use Template" to populate your note with structured content
4. **Customize Content**: Edit the template content to match your specific needs

## 📋 Pre-built Templates

### 1. 📅 Team Standup Meeting (90% relevance)
**Perfect for:** Daily team check-ins, sprint updates, progress tracking
**Contains:**
- Attendee list with roles
- Yesterday's progress review
- Today's priorities
- Blockers and challenges
- Action items with assignees and due dates

### 2. 🎯 Project Kickoff Plan (85% relevance)
**Perfect for:** Project planning, feature development, initiative launches
**Contains:**
- Project overview with goals and timeline
- Technical requirements and architecture
- Team assignments and resources
- Milestone breakdown with deliverables
- Risk analysis and mitigation strategies

### 3. 📚 Learning Notes (80% relevance)
**Perfect for:** Technical learning, course notes, skill development
**Contains:**
- Learning objectives and goals
- Key concepts with code examples
- Practical applications and insights
- Resource links and references
- Summary and next steps

### 4. 💡 Idea Capture (75% relevance)
**Perfect for:** Startup ideas, feature concepts, creative brainstorming
**Contains:**
- Core concept and problem statement
- Market opportunity analysis
- Technical feasibility assessment
- Business model considerations
- Action plan and next steps

### 5. 📊 Weekly Review (70% relevance)
**Perfect for:** Personal productivity, goal tracking, reflection
**Contains:**
- Goals accomplished, in progress, and missed
- Key metrics and achievements
- Insights and learnings
- Habit tracking
- Next week's focus areas

## 🎨 Creating Custom Templates

### The 4-Step Creation Wizard

#### Step 1: Basic Information (25% Complete)
**Smart Analysis**: The system analyzes your current note content and provides intelligent suggestions.

**Configure:**
- **Template Name**: Descriptive name for your template
- **Emoji & Category**: Visual identifier and classification
- **Description**: Purpose and use cases for the template
- **Keywords**: Extracted automatically from your content

**Smart Suggestions Examples:**
- Content with "meeting" → suggests 📅 Meeting Notes template
- Content with "project" → suggests 🎯 Project Plan template
- Content with "learn" → suggests 📚 Learning Notes template

#### Step 2: Content Structure (50% Complete)
**Live Editor**: Split-screen interface with content editor and real-time preview.

**Features:**
- **Template Editor**: Full markdown support with {variable} syntax
- **Quick Insert Buttons**:
  - **Section**: `## 📝 {section_title}`
  - **Checkbox**: `- [ ] {task}`
  - **Field**: `**{label}:** {value}`
  - **Footer**: `*{footer_note}*`
- **Common Variables**: One-click insertion of {date}, {time}, {title}, {author}
- **Live Preview**: See formatted output as you type

**Variable Syntax:**
```markdown
# {title} - {date}

## 📅 Meeting Details
**Project:** {project_name}
**Duration:** {duration}
**Attendees:** {attendees}

## 📝 Discussion Notes
{discussion_content}

## ✅ Action Items
- [ ] {action_1} - @{assignee_1} - Due: {due_date_1}
- [ ] {action_2} - @{assignee_2} - Due: {due_date_2}
```

#### Step 3: Variables & Preview (75% Complete)
**Variable Detection**: Automatically identifies variables from your template content.

**Variable Configuration:**
- **Auto-Detection**: Finds patterns like `{project_name}`, `{deadline}`
- **Default Values**: Set fallback values for each variable
- **Descriptions**: Document what each variable represents
- **Final Preview**: Review complete template with sample data

#### Step 4: Save Template (100% Complete)
**Template Summary**: Review all details before saving.

**Information Displayed:**
- Template name, category, and description
- Number of variables detected
- Usage instructions
- Preview of template content

**Save Options:**
- Templates save locally in browser session
- Immediately appear in Smart Templates list
- Searchable by name, description, and content
- Can be used instantly after creation

### Template Creation Best Practices

#### 1. Use Meaningful Variable Names
```markdown
# Good
{project_name}, {start_date}, {team_lead}

# Avoid
{thing}, {date1}, {person}
```

#### 2. Provide Structure and Context
```markdown
# Good
## 🎯 Objectives
1. {primary_goal}
2. {secondary_goal}

## 📊 Success Metrics
- {metric_1}: {target_1}
- {metric_2}: {target_2}

# Basic
Goals: {goals}
Metrics: {metrics}
```

#### 3. Include Helpful Prompts
```markdown
## 💡 Key Insights
*What did you learn that wasn't expected?*
{insights}

## 🚧 Challenges Encountered
*What obstacles did you face and how did you solve them?*
{challenges}
```

#### 4. Add Consistent Formatting
```markdown
---
**Template:** {template_name}
**Created:** {date} at {time}
**Author:** {author}
---
```

## 🔍 Search and Discovery

### Search Functionality
The Smart Templates search works across multiple data points:

**Search Targets:**
- Template names and descriptions
- Template categories and types
- Template content and structure
- Variable names and contexts

**Search Examples:**
- `"react"` → Shows React learning template
- `"meeting"` → Shows standup and project planning templates
- `"startup"` → Shows idea capture and business planning templates
- `"javascript"` → Finds templates with JS code examples
- `"api"` → Locates templates mentioning API development

### Context-Aware Suggestions
Templates automatically adapt based on:

**Time Context:**
- **Morning (6 AM - 12 PM)**: Standup meetings, daily planning
- **Afternoon (12 PM - 6 PM)**: Project work, learning sessions
- **Evening (6 PM - 10 PM)**: Reviews, retrospectives

**Content Analysis:**
- Keyword matching in your current note
- Writing patterns and structure
- Previous template usage patterns

**Usage Patterns:**
- Frequently used templates appear higher in results
- Templates adapt to your specific workflows
- Learning from your customization patterns

## 💪 Advanced Features

### Variable System
Templates support dynamic content replacement through variables:

**Common Variables:**
- `{date}` → Current date (2024-01-15)
- `{time}` → Current time (14:30)
- `{title}` → Extracted from content or user input
- `{author}` → Current user name

**Content-Aware Variables:**
- `{meeting_title}` → Detected from calendar or content
- `{attendees}` → Participant list from context
- `{project_name}` → Extracted from project references

### Template Analytics
Track your template usage patterns:
- Most frequently used templates
- Usage by time of day and context
- Template effectiveness metrics
- Customization patterns

### Integration Features
Smart Templates integrate with:
- **Apple Shortcuts**: Use templates in iOS workflows
- **Obsidian Sync**: Templates sync with your Obsidian vault
- **Calendar Events**: Context-aware meeting templates
- **Search System**: Template content is fully searchable

## 🛠️ Technical Implementation

### Template Structure
Templates are stored as JSON objects with metadata:

```json
{
  "template_id": "custom_meeting_notes",
  "name": "📅 Team Meeting Notes",
  "description": "Structured template for team meetings with action items",
  "type": "meeting",
  "content": "# {meeting_title} - {date}\n\n## Attendees\n{attendees}\n\n...",
  "variables": ["meeting_title", "date", "attendees"],
  "keywords": ["meeting", "team", "standup", "sync"],
  "usage_count": 15,
  "relevance_score": 0.9
}
```

### Variable Replacement
When a template is applied:
1. Variables are identified using `{variable_name}` syntax
2. Context-aware values are suggested or auto-filled
3. User can customize variables before application
4. Final content is generated with all variables replaced

### Search Algorithm
Template search uses weighted scoring:
- **Keyword matches**: 40% weight
- **Time context**: 20% weight
- **Calendar events**: 20% weight
- **Usage patterns**: 10% weight
- **Content analysis**: 10% weight

## 🎯 Use Cases and Examples

### Daily Workflows

#### Morning Standup
**Trigger**: Type "standup" or open templates at 9 AM
**Template**: Team Standup Meeting
**Result**: Structured meeting notes with yesterday/today/blockers format

#### Project Planning
**Trigger**: Type "project plan" or select project category
**Template**: Project Kickoff Plan
**Result**: Comprehensive project structure with timeline and resources

#### Learning Session
**Trigger**: Type "learn" or "study", or access during afternoon hours
**Template**: Learning Notes
**Result**: Structured learning format with objectives and examples

### Custom Workflows

#### Bug Report Template
Create a custom template for consistent bug reporting:

```markdown
# 🐛 Bug Report - {bug_title}

## 📝 Description
{bug_description}

## 🔄 Steps to Reproduce
1. {step_1}
2. {step_2}
3. {step_3}

## ✅ Expected Behavior
{expected_behavior}

## ❌ Actual Behavior
{actual_behavior}

## 🔧 Environment
- **OS**: {operating_system}
- **Browser**: {browser_version}
- **Version**: {app_version}

## 📷 Screenshots
{screenshots}

## 🔍 Additional Context
{additional_context}

---
**Priority**: {priority_level}
**Assignee**: {assignee}
**Created**: {date} by {reporter}
```

#### 1-on-1 Meeting Template
Regular team member check-ins:

```markdown
# 👥 1-on-1: {team_member} - {date}

## 🎯 Agenda
- {agenda_item_1}
- {agenda_item_2}
- {agenda_item_3}

## 💬 Discussion Points
### Recent Work & Achievements
{recent_work}

### Challenges & Blockers
{challenges}

### Career Development
{career_discussion}

### Feedback (Both Directions)
{feedback_exchange}

## ✅ Action Items
- [ ] {action_1} - {owner_1} - {due_date_1}
- [ ] {action_2} - {owner_2} - {due_date_2}

## 📅 Next Meeting
**Date**: {next_meeting_date}
**Focus**: {next_focus_area}

---
**Duration**: {meeting_duration}
**Mood**: {team_member_mood}/10
```

## 📈 Benefits and ROI

### Time Savings
- **Note Creation**: 5x faster with structured templates
- **Consistency**: Eliminate formatting decisions
- **Memory**: Never forget important sections again

### Quality Improvements
- **Professional Structure**: Templates ensure complete coverage
- **Searchability**: Consistent formatting improves findability
- **Collaboration**: Team members know what to expect

### Learning and Growth
- **Best Practices**: Templates encode proven structures
- **Knowledge Transfer**: Share effective formats across team
- **Continuous Improvement**: Templates evolve with usage

## 🔧 Troubleshooting

### Common Issues

#### Templates Not Loading
**Problem**: "Failed to load templates" message
**Solution**: Templates now use demo content by default - should work immediately

#### Search Not Working
**Problem**: Search returns no results
**Solution**: Search works across names, descriptions, and content - try broader terms

#### Variables Not Replacing
**Problem**: {variables} appear as literal text
**Solution**: Ensure variables use exact {variable_name} format without spaces

#### Custom Templates Disappearing
**Problem**: Created templates don't persist
**Solution**: Templates save in browser session - will need database integration for persistence

### Getting Help
- Check browser console for JavaScript errors
- Verify you're using a supported browser (Chrome, Firefox, Safari)
- Clear browser cache if templates seem outdated
- Report issues with specific steps to reproduce

## 🚀 Future Roadmap

### Near-term Enhancements
- **Persistent Storage**: Save custom templates permanently
- **Template Sharing**: Export/import templates between users
- **AI Suggestions**: More intelligent template recommendations
- **Template Categories**: Better organization and discovery

### Advanced Features
- **Template Inheritance**: Base templates with variations
- **Conditional Variables**: Show/hide sections based on context
- **Integration Expansion**: More third-party service connections
- **Collaborative Templates**: Team-shared template libraries

---

## 📝 Quick Reference

### Keyboard Shortcuts
- **Open Templates**: Click purple "Smart Templates" button
- **Search Templates**: Type in search box (searches all content)
- **Create Template**: Click green "Create Template" button
- **Apply Template**: Click "Use Template" on any template

### Template Syntax
- **Variables**: `{variable_name}`
- **Headers**: `# Title` or `## Section`
- **Checkboxes**: `- [ ] Task item`
- **Bold**: `**important text**`
- **Separators**: `---`

### Best Practices
1. Start with existing templates and customize
2. Use descriptive variable names
3. Include helpful prompts and context
4. Test templates before saving
5. Keep templates focused on specific use cases

*Last updated: 2024-01-15*
*Version: 1.0*