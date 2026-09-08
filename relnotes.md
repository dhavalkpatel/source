# {{buildDetails.definition.name}} release notes

## Build Details
- **Pipeline**: {{buildDetails.definition.name}}
- **Build Number**: {{buildDetails.buildNumber}}
- **Build ID**: {{buildDetails.id}}
- **Branch**: {{buildDetails.sourceBranch}}
- **Tags**: {{buildDetails.tags}}
- **Completed**: {{buildDetails.finishTime}}
- **Build Trigger PR Number**: {{lookup buildDetails.triggerInfo 'pr.number'}}
{{#if compareBuildDetails}}
- **Previous Build**: {{compareBuildDetails.buildNumber}}
- **Previous Build ID**: {{compareBuildDetails.id}}
{{/if}}
{{#if currentStage}}
- **Deployment Stage**: {{currentStage.name}}
{{/if}}

{{#if pullRequests.length}}
## Associated Pull Requests ({{pullRequests.length}})
{{#forEach pullRequests}}
- **[{{this.pullRequestId}}]({{replace (replace this.url "_apis/git/repositories" "_git") "pullRequests" "pullRequest"}})** {{this.title}}
  - Associated work items:
{{#forEach this.associatedWorkitems}}
  {{#with (lookup_a_work_item ../../relatedWorkItems this.url)}}
    - [{{this.id}}]({{replace this.url "_apis/wit/workItems" "_workitems/edit"}}) {{lookup this.fields 'System.Title'}}
  {{/with}}
{{/forEach}}
  - Associated commits:
{{#forEach this.associatedCommits}}
    - [{{truncate this.commitId 7}}]({{this.remoteUrl}}) {{get_only_message_firstline this.comment}}
{{/forEach}}
{{/forEach}}
{{/if}}

{{#if inDirectlyAssociatedPullRequests.length}}
## Indirectly Associated Pull Requests ({{inDirectlyAssociatedPullRequests.length}})
{{#forEach inDirectlyAssociatedPullRequests}}
- **{{this.pullRequestId}}** {{this.title}}
{{/forEach}}
{{/if}}

{{#if consumedArtifacts.length}}
## Consumed Artifacts ({{consumedArtifacts.length}})
| Category | Type | Version | Commits | Work Items |
|-|-|-|-|-|
{{#forEach consumedArtifacts}}
| {{this.artifactCategory}} | {{this.artifactType}} | {{this.versionName}} | {{this.commits.length}} | {{this.workitems.length}} |
{{/forEach}}
{{/if}}

{{#if workItems.length}}
## Associated Work Items ({{workItems.length}})
{{#forEach workItems}}
- **[{{this.id}}]({{replace this.url "_apis/wit/workItems" "_workitems/edit"}})** {{lookup this.fields 'System.Title'}}
  - **Type:** {{lookup this.fields 'System.WorkItemType'}}
  - **Tags:** {{lookup this.fields 'System.Tags'}}
  - **Assigned:** {{#with (lookup this.fields 'System.AssignedTo')}}{{displayName}}{{/with}}
  - **Description:** {{{lookup this.fields 'System.Description'}}}
  - **Pull Requests:**
{{#forEach this.relations}}
  {{#if (contains this.attributes.name 'Pull Request')}}
    {{#with (lookup_a_pullrequest ../../pullRequests this.url)}}
      - {{this.pullRequestId}} {{this.title}}
    {{/with}}
  {{/if}}
{{/forEach}}
  - **Parents:**
{{#forEach this.relations}}
  {{#if (contains this.attributes.name 'Parent')}}
    {{#with (lookup_a_work_item ../../relatedWorkItems this.url)}}
      - {{this.id}} {{lookup this.fields 'System.Title'}}
      {{#forEach this.relations}}
        {{#if (contains this.attributes.name 'Parent')}}
          {{#with (lookup_a_work_item ../../../../relatedWorkItems this.url)}}
            - {{this.id}} {{lookup this.fields 'System.Title'}}
          {{/with}}
        {{/if}}
      {{/forEach}}
    {{/with}}
  {{/if}}
{{/forEach}}
  - **Children:**
{{#forEach this.relations}}
  {{#if (contains this.attributes.name 'Child')}}
    {{#with (lookup_a_work_item ../../relatedWorkItems this.url)}}
      - {{this.id}} {{lookup this.fields 'System.Title'}}
    {{/with}}
  {{/if}}
{{/forEach}}
  - **Tested By:**
{{#forEach this.relations}}
  {{#if (contains this.attributes.name 'Tested By')}}
    {{#with (lookup_a_work_item ../../testedByWorkItems this.url)}}
      - {{this.id}} {{lookup this.fields 'System.Title'}}
    {{/with}}
  {{/if}}
{{/forEach}}
{{/forEach}}
{{/if}}

{{#if commits.length}}
## Associated Commits ({{commits.length}})
{{#forEach commits}}
- **{{this.id}}**
  - **Message:** {{this.message}}
  - **Committed by:** {{this.author.displayName}}
  - **Files changed:** {{this.changes.length}}
{{#forEach this.changes}}
    - **Path:** {{this.item.path}}{{this.filename}}
{{/forEach}}
{{/forEach}}
{{/if}}

{{#if tests.length}}
## Automated Tests ({{tests.length}})
{{#forEach tests}}
- **{{this.id}}** {{this.testCase.name}}: {{this.outcome}}
{{/forEach}}
{{/if}}

{{#if manualTests.length}}
## Manual Test Plans ({{manualTests.length}})
| Run ID | Name | State | Total | Passed |
|-|-|-|-|-|
{{#forEach manualTests}}
| [{{this.id}}]({{this.webAccessUrl}}) | {{this.name}} | {{this.state}} | {{this.totalTests}} | {{this.passedTests}} |
{{/forEach}}
{{/if}}

{{#if queryWorkItems.length}}
## Work Items Returned by WIQL ({{queryWorkItems.length}})
{{#forEach queryWorkItems}}
- **{{this.id}}** {{lookup this.fields 'System.Title'}}
{{/forEach}}
{{/if}}

{{#if publishedArtifacts.length}}
## Published Artifacts ({{publishedArtifacts.length}})
| Name | Type |
|-|-|
{{#forEach publishedArtifacts}}
| {{this.name}} | {{this.resource.type}} |
{{/forEach}}
{{/if}}
