"""Модуль для экспорта данных"""
import pandas as pd
import xlsxwriter
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from io import BytesIO
from datetime import datetime
from logger_config import setup_logger

logger = setup_logger()


class ExportManager:
    """Менеджер экспорта данных в различные форматы"""
    
    @staticmethod
    def export_to_csv(data, filename=None):
        """Экспорт данных в CSV"""
        try:
            df = pd.DataFrame(data)
            buffer = BytesIO()
            df.to_csv(buffer, index=False, encoding='utf-8-sig')
            buffer.seek(0)
            
            if filename:
                with open(filename, 'wb') as f:
                    f.write(buffer.read())
                logger.info(f"Данные экспортированы в CSV: {filename}")
                return filename
            else:
                return buffer
        except Exception as e:
            logger.error(f"Ошибка экспорта в CSV: {str(e)}")
            raise
    
    @staticmethod
    def export_to_excel(data, filename=None):
        """Экспорт данных в Excel"""
        try:
            df = pd.DataFrame(data)
            buffer = BytesIO()
            
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='Данные', index=False)
                
                workbook = writer.book
                worksheet = writer.sheets['Данные']
                
                # Форматирование
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#2066B0',
                    'font_color': 'white',
                    'border': 1
                })
                
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Автоширина колонок
                for i, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).map(len).max(),
                        len(col)
                    ) + 2
                    worksheet.set_column(i, i, max_length)
            
            buffer.seek(0)
            
            if filename:
                with open(filename, 'wb') as f:
                    f.write(buffer.read())
                logger.info(f"Данные экспортированы в Excel: {filename}")
                return filename
            else:
                return buffer
        except Exception as e:
            logger.error(f"Ошибка экспорта в Excel: {str(e)}")
            raise
    
    @staticmethod
    def export_to_pdf(data, title="Отчет о активности клещей", filename=None):
        """Экспорт данных в PDF"""
        try:
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            story = []
            
            # Стили
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.HexColor('#2066B0'),
                spaceAfter=30,
                alignment=1  # Центр
            )
            
            # Заголовок
            story.append(Paragraph(title, title_style))
            story.append(Spacer(1, 0.2*inch))
            
            # Дата генерации
            date_style = ParagraphStyle(
                'DateStyle',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.grey,
                alignment=1
            )
            story.append(Paragraph(
                f"Сгенерировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                date_style
            ))
            story.append(Spacer(1, 0.3*inch))
            
            # Таблица данных
            if data:
                df = pd.DataFrame(data)
                
                # Подготовка данных для таблицы
                table_data = [list(df.columns)]
                for _, row in df.iterrows():
                    table_data.append([str(val) for val in row])
                
                # Создание таблицы
                table = Table(table_data)
                table.setStyle(TableStyle([
                    # Заголовок
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2066B0')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    # Данные
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('FONTSIZE', (0, 1), (-1, -1), 10),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
                ]))
                
                story.append(table)
            
            # Генерация PDF
            doc.build(story)
            buffer.seek(0)
            
            if filename:
                with open(filename, 'wb') as f:
                    f.write(buffer.read())
                logger.info(f"Данные экспортированы в PDF: {filename}")
                return filename
            else:
                return buffer
        except Exception as e:
            logger.error(f"Ошибка экспорта в PDF: {str(e)}")
            raise

