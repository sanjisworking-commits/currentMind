# Product Requirements Document (PRD)

**Project:** CurrentMind
**Version:** 1.0 (Phase 1 – MVP)
**Author:** Musa
**Status:** Draft
**Last Updated:** July 2026

---

# 1. Introduction

## Overview

CurrentMind is a personal AI-powered learning system that transforms UPSC current affairs articles into structured, exam-oriented knowledge.

Rather than functioning as a traditional news reader, CurrentMind converts every article into a reusable learning object that helps users understand, revise, and retain important concepts.

The application is designed around one central philosophy:

> **The goal is not to read more news. The goal is to learn more from every article.**

CurrentMind will initially focus on a single trusted source—Indian Express UPSC Current Affairs—and later expand to additional sources while remaining independent of larger knowledge-management systems such as KOS.

---

# 2. Problem Statement

UPSC aspirants spend a significant portion of their study time reading newspapers and preparing current affairs notes manually.

The current workflow has several problems:

* Articles contain substantial journalistic information that is not directly relevant to the examination.
* Students must independently identify important static concepts, constitutional provisions, government schemes, reports, and international linkages.
* Manual note-making is time-consuming and inconsistent.
* Revision becomes increasingly difficult as the volume of articles grows.
* There is no structured personal knowledge base that accumulates over time.

CurrentMind aims to eliminate these inefficiencies by automatically converting articles into exam-ready learning notes.

---

# 3. Vision

To create an AI-powered learning companion that automatically transforms current affairs into structured UPSC knowledge.

Every processed article should answer the following questions:

* What happened?
* Why is it important?
* Which GS Paper does it belong to?
* Which static concepts should I revise?
* Which constitutional provisions are relevant?
* Which government schemes, committees, reports or international organisations are connected?
* What kind of Prelims and Mains questions can UPSC ask from this topic?

Ultimately, CurrentMind should evolve into a continuously growing personal knowledge base.

---

# 4. Product Philosophy

CurrentMind is built around five core principles.

## Learning First

Every feature should improve conceptual understanding rather than increase reading volume.

## Structured Knowledge

Information should be organised into reusable learning components instead of long-form summaries.

## Revision Friendly

Every article should be easy to revise weeks or months later.

## Incremental Learning

Each processed article should strengthen the user's existing understanding rather than exist in isolation.

## Simplicity

The application should remain simple, reliable and easy to maintain.

---

# 5. Objectives

## Primary Objective

Reduce the time required to study current affairs while improving conceptual understanding and long-term retention.

## Success Definition

A student should be able to understand an important UPSC article within **5–7 minutes** using CurrentMind instead of spending **20–30 minutes** reading and making notes manually.

---

# 6. Target Users

Primary Users

* UPSC Civil Services Aspirants

Secondary Users

* State PSC Aspirants
* CAPF Aspirants
* CDS Aspirants
* Public Policy Students
* Anyone preparing for competitive examinations requiring current affairs

---

# 7. Scope (Phase 1)

Phase 1 focuses on building a complete end-to-end pipeline for a single news source.

Workflow:

RSS Feed

↓

Detect New Article

↓

Download Article

↓

Extract Clean Content

↓

Analyze with LLM

↓

Generate Learning Note

↓

Store Locally

↓

Display in Dashboard

No additional intelligence beyond this pipeline will be implemented in Phase 1.

---

# 8. Functional Requirements

## 8.1 RSS Monitoring

The system shall monitor the Indian Express UPSC Current Affairs RSS feed.

Requirements:

* Fetch newly published articles.
* Prevent duplicate processing.
* Store article metadata.
* Maintain processing history.

Stored metadata:

* Title
* URL
* Author
* Publication Date
* Categories

---

## 8.2 Article Extraction

The application shall download and clean the article content.

Extract:

* Title
* Author
* Publication Date
* Main Article Body
* Categories

Ignore:

* Advertisements
* Navigation
* Footer
* Related Stories
* Comments

Output:

A clean article suitable for LLM analysis.

---

## 8.3 AI Analysis

Each article shall be transformed into a structured Learning Note.

The Learning Note shall contain:

### Executive Summary

A concise explanation of the article.

### Why It Matters

Explain the significance from the UPSC examination perspective.

### GS Paper Mapping

Identify the relevant General Studies paper.

### Syllabus Mapping

Associate the article with UPSC syllabus keywords.

### Static Concepts

List concepts that require revision.

### Constitutional Linkages

Relevant Articles, Amendments, Schedules or Judgments.

### Government Schemes

Related schemes, missions or programmes.

### Reports and Committees

Important reports, commissions and committees connected to the topic.

### International Dimension

Relevant organisations, treaties, conventions and geopolitical context.

### Important Facts

Data, statistics and factual points worth remembering.

### Prelims Preparation

Generate UPSC-style multiple-choice questions with answers and explanations.

### Mains Preparation

Generate analytical UPSC Mains questions.

### Revision Notes

Produce concise revision-ready notes.

### Keywords

Extract searchable topic keywords.

---

## 8.4 Storage

The application shall store:

* Original Article
* Metadata
* AI Learning Note

SQLite shall be used during Phase 1.

---

## 8.5 Dashboard

The dashboard shall provide:

### Home Page

Display:

* Recent Articles
* Publication Date
* GS Paper
* Tags
* Summary

### Article View

Display:

* Complete Learning Note
* Prelims Questions
* Mains Questions
* Revision Notes

---

# 9. Out of Scope

The following features are intentionally excluded from Phase 1:

* Multiple News Sources
* AI Chat
* Knowledge Graph
* Embeddings
* Semantic Search
* Vector Database
* Flashcards
* Spaced Repetition
* Revision Scheduling
* Authentication
* User Accounts
* Mobile Applications
* Browser Extensions

These capabilities will be introduced only after the core pipeline is stable.

---

# 10. Success Metrics

The MVP will be considered successful if it can:

* Detect newly published articles.
* Extract clean article content reliably.
* Generate structured AI Learning Notes.
* Store all processed articles locally.
* Display them through a simple dashboard.

From a user perspective, the application should reduce current affairs study time while improving conceptual clarity.

---

# 11. Long-Term Vision

CurrentMind is intended to become more than a summarisation tool.

Future versions may include:

* Multiple news sources
* Cross-article concept linking
* Knowledge graphs
* Semantic search
* Flashcards
* Spaced repetition
* AI tutor
* Revision planner
* Integration with the broader KOS ecosystem

However, every future enhancement should preserve the central philosophy:

> **Convert information into understanding, and understanding into long-term knowledge.**
