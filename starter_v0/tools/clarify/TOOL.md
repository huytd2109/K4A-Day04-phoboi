---
name: clarify
track: core
kind: control
requires_env: []
inputs: [question, response_type, options]
outputs: [question, response_type, options, awaiting_user]
side_effect: false
---
# clarify

Returns a question to the user and pauses until the next user turn.
Model calls must include both `question` and `response_type`. Use `text` for a
free-form identifier/value, `yes_no` for confirmation, and `choice` with a
non-empty `options` list for a closed enum.
