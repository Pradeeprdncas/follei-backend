# Follei Voice Recording and Dataset Guide

Status: recording specification
Purpose: define exactly which voices and performances Follei needs for Tamil/Tanglish TTS

## 1. Which voices are required

Follei needs three evaluation references and one eventual deployment speaker.

| Voice | Purpose | Minimum material |
|---|---|---:|
| Neutral Tamil voice A | Test Tamil quality independently of the final identity | 5 minutes plus a 10-30 second reference |
| Neutral Tamil voice B | Verify that quality is not tied to one reference | 5 minutes plus a 10-30 second reference |
| Neutral Tamil voice C | Compare gender/pitch/range and model stability | 5 minutes plus a 10-30 second reference |
| Owned Follei deployment voice | Final consented voice identity | 30-60 minute pilot, then 3-6 accepted hours |

The deployment speaker should be:

- A fluent conversational Tamil speaker.
- Comfortable with Tamil-English code switching.
- Able to sound warm, clear, trustworthy, and professional.
- Able to perform support, sales, empathy, confirmations, and collections without acting theatrically.
- Available for later correction sessions using the same recording setup.
- Explicitly contracted for AI training, commercial TTS, generated speech, and model updates.

Do not select only by attractive timbre. Pronunciation consistency, stamina, microphone discipline, and natural Tanglish matter more.

## 2. Consent package

Before recording, collect a signed agreement covering:

- Speaker legal identity and contact.
- Permission to record and process the sessions.
- Permission to train and evaluate TTS/voice models.
- Permission for commercial synthetic speech.
- Approved products, channels, territories, and duration.
- Whether sublicensing or customer-specific use is permitted.
- Compensation and future recording sessions.
- Prohibited uses.
- Withdrawal, deletion, and model-retirement procedure.
- Permission to retain reference audio and derived checkpoints.

Store the agreement outside the Git repository. The manifest stores only its internal evidence identifier and `rights_confirmed: true`.

## 3. Recording environment

Use one consistent room and setup for each dataset version.

Required conditions:

- Quiet, acoustically treated room.
- No fan, air conditioner, traffic, computer hum, music, or other speakers.
- Low, stable room reverb.
- Phone switched to silent and placed away from the microphone.
- Speaker seated or standing consistently across sessions.
- Water available; pause when mouth noise or fatigue increases.

Record 30-45 minute sessions with breaks. Very long sessions cause vocal drift and inconsistent energy.

## 4. Microphone and capture

Preferred capture:

- Cardioid condenser or broadcast-quality dynamic microphone.
- Pop filter.
- Fixed microphone stand.
- Approximately 15-20 cm mouth-to-microphone distance.
- Microphone slightly off-axis to reduce plosives.
- Audio interface with stable gain and no automatic gain control.
- Mono WAV, 48 kHz, 24-bit source recording.
- Peaks normally between approximately -12 and -6 dBFS.
- No clipping, limiter, compression, noise gate, reverb, EQ, or aggressive denoising during recording.

The processing pipeline creates 24 kHz, 16-bit PCM training copies. Keep the original masters unchanged.

Record ten seconds of room tone at the beginning and end of every session. Record a calibration sentence before starting so gain and distance can be checked.

## 5. Speaking style

The baseline voice should sound like a capable Tamil business representative, not a newsreader, audiobook narrator, radio advertisement, or imitation of another person.

General delivery:

- Natural Chennai/Tamil Nadu conversational Tamil unless another approved accent is selected.
- Medium pace with complete but not exaggerated articulation.
- Natural pauses at phrase boundaries.
- Warm and attentive energy.
- No forced bass, whispering, shouting, or artificial enthusiasm.
- English business words spoken as a fluent Tamil speaker would normally say them.
- Contractions and colloquial grammar used consistently.

Do three takes only when the script requests distinct delivery styles. Otherwise record one clean, natural take rather than many near-duplicates.

## 6. Required performance profiles

| Profile | Direction | Example intent |
|---|---|---|
| `conversational` | Neutral, warm, medium pace | Normal explanation |
| `support` | Patient, reassuring, slightly slower | Resolve a problem |
| `sales` | Positive and confident without pressure | Explain value and next step |
| `empathetic` | Softer energy and careful pauses | Acknowledge customer difficulty |
| `confirmation` | Clear and concise | Confirm date, number, or action |
| `collections` | Calm, respectful, firm | Explain overdue payment |

Do not encode these profiles only through one person's identity. They become independent prosody controls after the model proves it can represent them consistently.

## 7. Script composition

For the 3-6 hour production corpus, target:

| Content | Share |
|---|---:|
| Neutral conversational Tamil/Tanglish | 20% |
| Customer support and explanation | 20% |
| Sales and lead nurturing | 15% |
| Empathy, apology, reassurance | 15% |
| Questions and confirmations | 10% |
| Money, dates, time, phone numbers, percentages | 10% |
| Names, places, URLs, identifiers | 5% |
| GST, EMI, CRM, KYC, OTP and product vocabulary | 5% |

Include short, medium, and long utterances. Most accepted clips should be 2-12 seconds after segmentation.

Example lines:

```text
சார், உங்க payment இன்னும் process ஆகல.
நான் ஒரு இரண்டு நிமிஷத்துல check பண்ணிட்டு சொல்றேன்.
Annual plan-க்கு three months EMI option இருக்கு.
உங்களுக்கு வந்த ஆறு digit OTP-யை சொல்ல முடியுமா?
நாளைக்கு afternoon three thirty-க்கு call பண்ணலாமா?
இந்த issue உங்களுக்கு கஷ்டமா இருந்திருக்கும்; நான் இப்பவே help பண்ணுறேன்.
```

The production script must also cover Tamil phoneme combinations, different sentence endings, questions, enumerations, abbreviations, and natural code-switch boundaries.

## 8. Transcript rules

The transcript must contain exactly what the speaker said.

Preferred representation:

```text
உங்க account-ல இன்னும் payment வரல சார்.
```

Rules:

- Tamil grammar and spoken words use Tamil script.
- Familiar English business words remain in Latin script.
- Preserve spoken contractions; do not rewrite them into literary Tamil.
- Write numbers in the form intended for TTS normalization and evaluation.
- Do not remove repetitions that remain in the accepted audio.
- Do not include punctuation that implies a pause the speaker did not make.
- Reject the clip when the transcript cannot be made exact confidently.

Romanized Tamil input is an application feature, not the primary acoustic training transcript. A separate frontend will normalize `unga payment innum varala` into the mixed-script form.

## 9. Clip acceptance

Accept only clips that have:

- Exactly one approved speaker.
- No overlap or background speech.
- No music or sound effects.
- No clipping or digital corruption.
- Low room noise and stable reverb.
- Natural beginning and ending without cut phonemes.
- Exact transcript.
- Consistent speaker identity and intended profile.
- Duration between 2 and 12 seconds unless an evaluation case explicitly requires longer speech.

Reject clips with aggressive AI denoising artifacts. Cleaning cannot repair every source; re-recording is preferable.

## 10. Licensed online video

Use online video only when the license explicitly permits AI training and the intended commercial use.

Do not combine videos into one long file. Process each source separately:

```text
video
  -> audio extraction
  -> vocal separation
  -> VAD
  -> target-speaker verification
  -> overlap/music/noise rejection
  -> exact transcript correction
  -> approved 2-12 second clips
```

Online material mixes identity, accent, rhythm, room sound, compression, and editing style. It cannot be assumed to teach accent without also teaching recognizable identity. Purpose-recorded owned data is the preferred production source.

## 11. Dataset split and naming

Use source/session-level splits:

- Training: approximately 90%.
- Validation: approximately 5%.
- Test: approximately 5%.

Do not split near-duplicate takes across sets. A complete recording session belongs to only one split.

Recommended IDs:

```text
speaker-session-profile-line-take.wav
follei01-s01-support-0042-t01.wav
```

Every accepted clip must map to its source/session, transcript, speaker, language, split, rights record, and performance profile.

## 12. Delivery package from the recording team

Provide:

1. Original untouched session WAV files.
2. Session sheet with microphone, interface, gain, room, date, and speaker condition.
3. Script and take log.
4. Ten seconds of room tone per session.
5. Edited but not destructively denoised candidate clips.
6. Exact UTF-8 transcripts.
7. Source/session-level split assignment.
8. Consent evidence identifier.
9. Notes for mispronunciations, retakes, and unusual delivery.

The ML team runs manifest validation before any GPU experiment. Audio delivery alone is not a trainable dataset.

## 13. First recording milestone

The first useful delivery is:

- Three owned neutral references of 10-30 seconds with exact transcripts.
- Five minutes from each neutral evaluation voice.
- Thirty to sixty minutes from the selected deployment speaker.
- Coverage of all six performance profiles and the critical business-entity suite.
- Clean master audio, candidate clips, transcripts, session metadata, and consent record.

This pilot is evaluated with IndicF5 before expanding to 3-6 hours.
