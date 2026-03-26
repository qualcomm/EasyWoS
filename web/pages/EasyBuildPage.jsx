import React, { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { Card, Spin, message, Anchor } from 'antd';
import remarkGfm from 'remark-gfm';
import rehypeSlug from 'rehype-slug';
import rehypeAutolinkHeadings from 'rehype-autolink-headings';

const EasyBuildPage = () => {
    const [markdown, setMarkdown] = useState('');
    const [loading, setLoading] = useState(true);
    const [tocItems, setTocItems] = useState([]);

    useEffect(() => {
        const fetchMarkdown = async () => {
            try {
                const response = await fetch('/static/easybuild-en.md');
                if (response.ok) {
                    const text = await response.text();
                    setMarkdown(text);
                    // Generate TOC from markdown headings
                    generateTOC(text);
                } else {
                    message.error('Failed to load document.');
                }
            } catch (error) {
                console.error('Error loading markdown:', error);
                message.error('Network error loading document.');
            } finally {
                setLoading(false);
            }
        };

        fetchMarkdown();
    }, []);

    const generateTOC = (markdownText) => {
        // Match markdown headings, but exclude lines that are comments or separators
        const lines = markdownText.split(/\r?\n/);
        const items = [];

        lines.forEach((line) => {
            // Match heading pattern: starts with 1-6 # followed by space and text
            // Using trim() on the line first handles potential trailing whitespace issues
            const match = line.trim().match(/^(#{1,6})\s+(.+)$/);
            
            if (match) {
                const level = match[1].length;
                const title = match[2].trim();
                
                // Skip if title contains only dashes or special characters (likely a comment)
                if (/^[-\s]+$/.test(title) || title.startsWith('---')) {
                    return;
                }
                
                const id = title.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '-');
                
                items.push({
                    key: id,
                    href: `#${id}`,
                    title: title,
                    level: level
                });
            }
        });

        setTocItems(items);
    };

    return (
        <div style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
            <div style={{ display: 'flex', gap: '24px' }}>
                {/* Table of Contents */}
                {tocItems.length > 0 && (
                    <Card 
                        bordered={false} 
                        style={{ 
                            width: '280px', 
                            position: 'sticky', 
                            top: '24px', 
                            height: 'fit-content',
                            maxHeight: 'calc(100vh - 120px)',
                            overflowY: 'auto'
                        }}
                    >
                        <h3 style={{ marginBottom: '16px', fontSize: '16px', fontWeight: 600 }}>Table of Contents</h3>
                        <Anchor
                            offsetTop={80}
                            items={tocItems.map(item => ({
                                key: item.key,
                                href: item.href,
                                title: item.title,
                                style: { paddingLeft: `${(item.level - 1) * 12}px` }
                            }))}
                        />
                    </Card>
                )}

                {/* Main Content */}
                <Card bordered={false} style={{ flex: 1 }}>
                    {loading ? (
                        <div style={{ textAlign: 'center', padding: '50px' }}>
                            <Spin size="large" />
                        </div>
                    ) : (
                        <div className="markdown-body">
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                rehypePlugins={[rehypeSlug, rehypeAutolinkHeadings]}
                            >
                                {markdown}
                            </ReactMarkdown>
                        </div>
                    )}
                </Card>
            </div>
        </div>
    );
};

export default EasyBuildPage;
